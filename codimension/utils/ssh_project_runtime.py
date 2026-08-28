# -*- coding: utf-8 -*-
#
# codimension - SSH remote project runtime (save upload + run)
# Copyright (C) 2026  Codimension Team
# The license is described in the LICENSE file at the root directory.
#

"""Wire remote-bound projects: Save→SFTP upload and Run over SSH (no IDE debug)."""

from __future__ import annotations

import logging
import os
import posixpath
import shlex
from typing import Optional, Sequence

from utils.globals import GlobalData
from utils.ssh_remote import (
    RemoteProjectBinding,
    SshHostProfile,
    connect_paramiko_sftp,
    load_host_profiles,
    load_ssh_password,
    open_paramiko_ssh_client,
    read_binding,
    require_paramiko,
    upload_file,
    upsert_host_profile,
)


def get_loaded_project_binding() -> Optional[RemoteProjectBinding]:
    """Return ``binding.json`` for the currently loaded project, if any."""
    project = GlobalData().project
    if project is None or not project.isLoaded():
        return None
    project_dir = project.getProjectDir()
    if not project_dir:
        return None
    return read_binding(project_dir.rstrip(os.sep))


def profile_from_binding(binding: RemoteProjectBinding) -> SshHostProfile:
    """Rebuild a host profile from a persisted binding (include saved host-key pin)."""
    pin = ""
    for saved in load_host_profiles():
        if saved.id == binding.profile_id:
            pin = saved.host_key_fingerprint
            break
    return SshHostProfile(
        id=binding.profile_id,
        host=binding.host,
        port=binding.port,
        user=binding.user,
        auth=binding.auth,
        identity_file=binding.identity_file,
        label=f"{binding.user + '@' if binding.user else ''}{binding.host}",
        host_key_fingerprint=pin,
    ).normalized()


def map_local_to_remote(binding: RemoteProjectBinding, local_path: str) -> str:
    """Map a local cache path to the corresponding remote POSIX path."""
    local = os.path.realpath(local_path)
    root = os.path.realpath(binding.local_root)
    root_prefix = root if root.endswith(os.sep) else root + os.sep
    if local != root and not local.startswith(root_prefix):
        raise ValueError(f"path is outside remote project cache: {local_path}")
    rel = os.path.relpath(local, root)
    if rel == os.curdir:
        return _norm(binding.remote_root)
    return _norm(posixpath.join(binding.remote_root, rel.replace(os.sep, "/")))


def is_under_binding(binding: RemoteProjectBinding, local_path: str) -> bool:
    """True when ``local_path`` lives inside the binding cache root."""
    try:
        map_local_to_remote(binding, local_path)
        return True
    except ValueError:
        return False


def after_save_upload_remote(_widget, file_name: str) -> None:
    """``afterSaveCallbacks`` hook: upload saved buffer when project is remote-bound."""
    binding = get_loaded_project_binding()
    if binding is None or not file_name:
        return
    if not is_under_binding(binding, file_name):
        return
    try:
        remote = map_local_to_remote(binding, file_name)
        _with_sftp(binding, lambda session: upload_file(session, file_name, remote))
        logging.info("SSH upload: %s → %s", file_name, remote)
    except Exception as exc:
        logging.error("SSH upload failed for %s: %s", file_name, exc)


def run_remote_script(
    binding: RemoteProjectBinding,
    local_script: str,
    args: Sequence[str] = (),
    *,
    python: str = "python3",
) -> tuple[int, str, str, str]:
    """Upload ``local_script`` and execute it on the remote host.

    Returns ``(exit_code, stdout, stderr, remote_script)``.
    """
    require_paramiko()
    remote_script = map_local_to_remote(binding, local_script)
    profile = profile_from_binding(binding)
    password = load_ssh_password(profile.id) if profile.auth == "password" else ""

    session = connect_paramiko_sftp(profile, password=password)
    try:
        upload_file(session, local_script, remote_script)
    finally:
        session.close()

    remote_cwd = _norm(posixpath.dirname(remote_script) or binding.remote_root)
    argv = [python, remote_script, *list(args)]
    code, stdout, stderr = _exec_remote(profile, password, argv, cwd=remote_cwd)
    return int(code), stdout, stderr, remote_script


def try_handle_ide_run(path: str, *, kind: str) -> bool:
    """If the loaded project is SSH-bound, handle RUN (not debug). Return True if handled."""
    binding = get_loaded_project_binding()
    if binding is None:
        return False
    if not is_under_binding(binding, path):
        # Script outside cache — fall back to local execution.
        return False

    if kind == "debug":
        logging.error(
            "SSH remote debug is not available yet. Use Run for remote execution, or open a local project to debug."
        )
        return True

    if kind == "profile":
        logging.error("SSH remote profile is not available yet. Use Run for remote execution.")
        return True

    # kind == run
    try:
        from utils.run import getRunParameters

        raw = getRunParameters(path)["arguments"]
        args = shlex.split(raw) if raw else []
    except Exception:
        args = []

    logging.info("SSH run starting for %s …", path)
    try:
        code, stdout, stderr, remote_script = run_remote_script(binding, path, args)
    except Exception as exc:
        logging.error("SSH run failed: %s", exc)
        return True

    _emit_run_output(remote_script, code, stdout, stderr)
    return True


def _emit_run_output(remote_script: str, code: int, stdout: str, stderr: str) -> None:
    """Send remote run output to the IDE log / redirected IO console when possible."""
    header = f"SSH run finished ({remote_script}) exit={code}"
    logging.info(header)
    if stdout:
        logging.info("SSH stdout:\n%s", stdout.rstrip())
    if stderr:
        logging.error("SSH stderr:\n%s", stderr.rstrip())

    mw = GlobalData().mainWindow
    if mw is None:
        return
    console = getattr(mw, "redirectedIOConsole", None)
    if console is None:
        return
    try:
        console.appendIDEMessage(header)
        if stdout:
            console.appendStdoutMessage(stdout)
        if stderr:
            console.appendStderrMessage(stderr)
    except Exception as exc:
        logging.debug("Could not write SSH output to IO console: %s", exc)


def _with_sftp(binding: RemoteProjectBinding, fn) -> None:
    profile = profile_from_binding(binding)
    password = load_ssh_password(profile.id) if profile.auth == "password" else ""
    session = connect_paramiko_sftp(profile, password=password)
    try:
        if getattr(session, "profile", None) is not None and session.profile.host_key_fingerprint:
            if session.profile.host_key_fingerprint != profile.host_key_fingerprint:
                upsert_host_profile(session.profile)
        fn(session)
    finally:
        session.close()


def _exec_remote(
    profile: SshHostProfile,
    password: str,
    argv: Sequence[str],
    *,
    cwd: Optional[str] = None,
) -> tuple[int, str, str]:
    """Run argv on the remote host via Paramiko (login-shell fragment)."""
    parts: list[str] = []
    if cwd:
        parts.extend(["cd", shlex.quote(cwd), "&&"])
    parts.extend(shlex.quote(part) for part in argv)
    remote = " ".join(parts)

    client, pinned = open_paramiko_ssh_client(profile, password=password)
    if pinned.host_key_fingerprint and pinned.host_key_fingerprint != profile.host_key_fingerprint:
        try:
            upsert_host_profile(pinned)
        except Exception:
            logging.debug("Could not persist SSH host key pin", exc_info=True)
    try:
        _stdin, stdout, stderr = client.exec_command(remote)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        code = stdout.channel.recv_exit_status()
        return int(code), out, err
    finally:
        client.close()


def _norm(path: str) -> str:
    text = (path or "").replace("\\", "/").strip()
    if not text:
        return "/"
    if not text.startswith("/"):
        text = "/" + text
    return posixpath.normpath(text)


__all__ = [
    "after_save_upload_remote",
    "get_loaded_project_binding",
    "is_under_binding",
    "map_local_to_remote",
    "profile_from_binding",
    "run_remote_script",
    "try_handle_ide_run",
]
