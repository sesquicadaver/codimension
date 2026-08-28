# -*- coding: utf-8 -*-
#
# codimension - SSH remote project runtime (save upload + run)
# Copyright (C) 2026  Codimension Team
# The license is described in the LICENSE file at the root directory.
#

"""Wire remote-bound projects: Save→SFTP upload and Run over SSH (no IDE debug).

R186 / A204: Save and Run are **async jobs** (background threads) so the GUI
thread is not blocked. Upload/run support cancel, timeout, and bounded
stdout/stderr. Local save success is distinct from remote ``SYNCED``.
"""

from __future__ import annotations

import logging
import os
import posixpath
import shlex
import threading
import time
from typing import Callable, Optional, Sequence

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

# Remote sync state for a local cache path (R186). Local disk save ≠ SYNCED.
SYNC_LOCAL = "LOCAL"
SYNC_SYNCING = "SYNCING"
SYNC_SYNCED = "SYNCED"
SYNC_FAILED = "SYNC_FAILED"
SYNC_CANCELLED = "SYNC_CANCELLED"

DEFAULT_SSH_JOB_TIMEOUT_SEC = 120
DEFAULT_SSH_MAX_OUTPUT_BYTES = 2 * 1024 * 1024  # 2 MiB per stream
ENV_SSH_TIMEOUT = "CDM_SSH_TIMEOUT_SEC"
ENV_SSH_MAX_OUTPUT = "CDM_SSH_MAX_OUTPUT_BYTES"
_POLL_INTERVAL_SEC = 0.05
_RECV_CHUNK = 65536

_sync_lock = threading.Lock()
_sync_states: dict[str, str] = {}
_jobs_lock = threading.Lock()
_upload_jobs: dict[str, "SshJobHandle"] = {}
_run_job: Optional["SshJobHandle"] = None


class SshRemoteJobCancelled(RuntimeError):
    """Raised when an SSH upload/run job is cancelled."""


class SshRemoteJobTimeout(RuntimeError):
    """Raised when an SSH upload/run job exceeds its timeout."""


class SshJobHandle:
    """Cancelable handle for one background SSH job."""

    def __init__(self, *, kind: str, path: str = "") -> None:
        self.kind = kind
        self.path = path
        self.cancel = threading.Event()
        self.done = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.error: Optional[BaseException] = None
        self.result: object = None

    def request_cancel(self) -> None:
        """Request cooperative cancellation."""
        self.cancel.set()

    def join(self, timeout: Optional[float] = None) -> bool:
        """Wait until the worker finishes. Return True if done."""
        return self.done.wait(timeout)


def resolve_ssh_job_limits(
    *,
    timeout_sec: Optional[float] = None,
    max_output_bytes: Optional[int] = None,
) -> tuple[float, int]:
    """Return ``(timeout_sec, max_output_bytes)``; ``0`` timeout = no deadline."""
    timeout = float(DEFAULT_SSH_JOB_TIMEOUT_SEC if timeout_sec is None else timeout_sec)
    limit = int(DEFAULT_SSH_MAX_OUTPUT_BYTES if max_output_bytes is None else max_output_bytes)
    if timeout_sec is None:
        raw = os.environ.get(ENV_SSH_TIMEOUT, "").strip()
        if raw:
            timeout = max(0.0, float(raw))
    if max_output_bytes is None:
        raw = os.environ.get(ENV_SSH_MAX_OUTPUT, "").strip()
        if raw:
            limit = max(0, int(raw))
    return max(0.0, timeout), max(0, limit)


def get_sync_state(file_name: str) -> str:
    """Return SYNC_* for ``file_name`` (default ``LOCAL``)."""
    key = os.path.realpath(file_name) if file_name else ""
    with _sync_lock:
        return _sync_states.get(key, SYNC_LOCAL)


def set_sync_state(file_name: str, state: str) -> None:
    """Record SYNC_* for ``file_name``."""
    if not file_name:
        return
    key = os.path.realpath(file_name)
    with _sync_lock:
        _sync_states[key] = state


def clear_sync_state(file_name: str = "") -> None:
    """Clear one path or all sync states (tests / project close)."""
    with _sync_lock:
        if not file_name:
            _sync_states.clear()
            return
        _sync_states.pop(os.path.realpath(file_name), None)


def cancel_ssh_upload(file_name: str) -> bool:
    """Cancel an in-flight upload for ``file_name``. Return True if a job existed."""
    key = os.path.realpath(file_name) if file_name else ""
    with _jobs_lock:
        handle = _upload_jobs.get(key)
    if handle is None:
        return False
    handle.request_cancel()
    return True


def cancel_ssh_run() -> bool:
    """Cancel the in-flight SSH Run job, if any."""
    with _jobs_lock:
        handle = _run_job
    if handle is None:
        return False
    handle.request_cancel()
    return True


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
    except ValueError:
        return False
    return True


def after_save_upload_remote(_widget, file_name: str) -> None:
    """``afterSaveCallbacks`` hook: schedule async SFTP upload (R186).

    Returns immediately. Local save success does **not** imply ``SYNCED`` —
    callers must read :func:`get_sync_state`.
    """
    binding = get_loaded_project_binding()
    if binding is None or not file_name:
        return
    if not is_under_binding(binding, file_name):
        return
    try:
        remote = map_local_to_remote(binding, file_name)
    except ValueError:
        return
    schedule_remote_upload(binding, file_name, remote)


def schedule_remote_upload(
    binding: RemoteProjectBinding,
    local_path: str,
    remote_path: str,
    *,
    timeout_sec: Optional[float] = None,
    on_finished: Optional[Callable[[str, str, Optional[BaseException]], None]] = None,
) -> SshJobHandle:
    """Start a background upload job; previous job for the same path is cancelled."""
    key = os.path.realpath(local_path)
    handle = SshJobHandle(kind="upload", path=key)
    with _jobs_lock:
        previous = _upload_jobs.get(key)
        _upload_jobs[key] = handle
    if previous is not None:
        previous.request_cancel()

    set_sync_state(local_path, SYNC_SYNCING)
    logging.info("SSH upload scheduled (SYNCING): %s → %s", local_path, remote_path)

    def _worker() -> None:
        err: Optional[BaseException] = None
        try:
            if handle.cancel.is_set():
                raise SshRemoteJobCancelled("SSH upload cancelled")
            timeout, _cap = resolve_ssh_job_limits(timeout_sec=timeout_sec)
            deadline = None if timeout <= 0 else time.monotonic() + timeout

            def _do_upload(session) -> None:
                if handle.cancel.is_set():
                    raise SshRemoteJobCancelled("SSH upload cancelled")
                if deadline is not None and time.monotonic() > deadline:
                    raise SshRemoteJobTimeout(f"SSH upload timed out after {timeout}s")
                upload_file(session, local_path, remote_path)

            _with_sftp(binding, _do_upload, cancel=handle.cancel, deadline=deadline)
            if handle.cancel.is_set():
                raise SshRemoteJobCancelled("SSH upload cancelled")
            set_sync_state(local_path, SYNC_SYNCED)
            logging.info("SSH upload SYNCED: %s → %s", local_path, remote_path)
        except SshRemoteJobCancelled as exc:
            err = exc
            set_sync_state(local_path, SYNC_CANCELLED)
            logging.warning("SSH upload cancelled: %s", local_path)
        except Exception as exc:
            err = exc
            set_sync_state(local_path, SYNC_FAILED)
            logging.error("SSH upload SYNC_FAILED for %s: %s", local_path, exc)
        finally:
            handle.error = err
            handle.done.set()
            with _jobs_lock:
                if _upload_jobs.get(key) is handle:
                    _upload_jobs.pop(key, None)
            state = get_sync_state(local_path)
            if on_finished is not None:
                _call_on_gui_thread(lambda: on_finished(local_path, state, err))

    thread = threading.Thread(target=_worker, name=f"ssh-upload:{os.path.basename(key)}", daemon=True)
    handle.thread = thread
    thread.start()
    return handle


def run_remote_script(
    binding: RemoteProjectBinding,
    local_script: str,
    args: Sequence[str] = (),
    *,
    python: str = "python3",
    cancel: Optional[threading.Event] = None,
    timeout_sec: Optional[float] = None,
    max_output_bytes: Optional[int] = None,
) -> tuple[int, str, str, str]:
    """Upload ``local_script`` and execute it on the remote host.

    Returns ``(exit_code, stdout, stderr, remote_script)``. Honours cancel,
    timeout, and output caps (R186).
    """
    require_paramiko()
    remote_script = map_local_to_remote(binding, local_script)
    profile = profile_from_binding(binding)
    password = load_ssh_password(profile.id) if profile.auth == "password" else ""
    timeout, out_cap = resolve_ssh_job_limits(timeout_sec=timeout_sec, max_output_bytes=max_output_bytes)
    deadline = None if timeout <= 0 else time.monotonic() + timeout
    cancel_event = cancel or threading.Event()

    def _do_upload(session) -> None:
        _raise_if_cancelled_or_timed_out(cancel_event, deadline, timeout, "upload")
        upload_file(session, local_script, remote_script)

    session = connect_paramiko_sftp(profile, password=password)
    try:
        _do_upload(session)
    finally:
        session.close()

    _raise_if_cancelled_or_timed_out(cancel_event, deadline, timeout, "run")
    remote_cwd = _norm(posixpath.dirname(remote_script) or binding.remote_root)
    argv = [python, remote_script, *list(args)]
    remaining = None if deadline is None else max(0.1, deadline - time.monotonic())
    code, stdout, stderr = _exec_remote(
        profile,
        password,
        argv,
        cwd=remote_cwd,
        cancel=cancel_event,
        timeout_sec=remaining if remaining is not None else timeout,
        max_output_bytes=out_cap,
    )
    return int(code), stdout, stderr, remote_script


def try_handle_ide_run(path: str, *, kind: str) -> bool:
    """If the loaded project is SSH-bound, handle RUN async (not debug). Return True if handled."""
    binding = get_loaded_project_binding()
    if binding is None:
        return False
    if not is_under_binding(binding, path):
        return False

    if kind == "debug":
        logging.error(
            "SSH remote debug is not available yet. Use Run for remote execution, or open a local project to debug."
        )
        return True

    if kind == "profile":
        logging.error("SSH remote profile is not available yet. Use Run for remote execution.")
        return True

    try:
        from utils.run import getRunParameters

        raw = getRunParameters(path)["arguments"]
        args = shlex.split(raw) if raw else []
    except Exception:
        args = []

    schedule_remote_run(binding, path, args)
    return True


def schedule_remote_run(
    binding: RemoteProjectBinding,
    local_script: str,
    args: Sequence[str] = (),
    *,
    timeout_sec: Optional[float] = None,
    max_output_bytes: Optional[int] = None,
    on_finished: Optional[Callable[[int, str, str, str, Optional[BaseException]], None]] = None,
) -> SshJobHandle:
    """Start a background SSH Run job (cancels any previous Run)."""
    global _run_job
    handle = SshJobHandle(kind="run", path=os.path.realpath(local_script))
    with _jobs_lock:
        previous = _run_job
        _run_job = handle
    if previous is not None:
        previous.request_cancel()

    logging.info("SSH run scheduled for %s …", local_script)

    def _worker() -> None:
        global _run_job
        err: Optional[BaseException] = None
        code = -1
        stdout = ""
        stderr = ""
        remote_script = ""
        try:
            code, stdout, stderr, remote_script = run_remote_script(
                binding,
                local_script,
                args,
                cancel=handle.cancel,
                timeout_sec=timeout_sec,
                max_output_bytes=max_output_bytes,
            )
            handle.result = (code, stdout, stderr, remote_script)
        except Exception as exc:
            err = exc
            handle.error = exc
            logging.error("SSH run failed: %s", exc)
        finally:
            handle.done.set()
            with _jobs_lock:
                if _run_job is handle:
                    _run_job = None

            def _finish() -> None:
                try:
                    if err is None:
                        _emit_run_output(remote_script, code, stdout, stderr)
                    else:
                        logging.error("SSH run error for %s: %s", local_script, err)
                        try:
                            mw = GlobalData().mainWindow
                            console = getattr(mw, "redirectedIOConsole", None) if mw else None
                            if console is not None:
                                console.appendIDEMessage(f"SSH run failed: {err}")
                        except Exception:
                            logging.debug("Could not write SSH run error to console", exc_info=True)
                finally:
                    if on_finished is not None:
                        on_finished(code, stdout, stderr, remote_script, err)

            _call_on_gui_thread(_finish)

    thread = threading.Thread(target=_worker, name="ssh-run", daemon=True)
    handle.thread = thread
    thread.start()
    return handle


def _emit_run_output(remote_script: str, code: int, stdout: str, stderr: str) -> None:
    """Send remote run output to the IDE log / redirected IO console when possible."""
    header = f"SSH run finished ({remote_script}) exit={code}"
    logging.info(header)
    if stdout:
        logging.info("SSH stdout:\n%s", stdout.rstrip())
    if stderr:
        logging.error("SSH stderr:\n%s", stderr.rstrip())

    try:
        mw = GlobalData().mainWindow
    except Exception:
        return
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


def _with_sftp(
    binding: RemoteProjectBinding,
    fn,
    *,
    cancel: Optional[threading.Event] = None,
    deadline: Optional[float] = None,
) -> None:
    _raise_if_cancelled_or_timed_out(cancel, deadline, None, "connect")
    profile = profile_from_binding(binding)
    password = load_ssh_password(profile.id) if profile.auth == "password" else ""
    session = connect_paramiko_sftp(profile, password=password)
    try:
        if getattr(session, "profile", None) is not None and session.profile.host_key_fingerprint:
            if session.profile.host_key_fingerprint != profile.host_key_fingerprint:
                upsert_host_profile(session.profile)
        _raise_if_cancelled_or_timed_out(cancel, deadline, None, "sftp")
        fn(session)
    finally:
        session.close()


def _exec_remote(
    profile: SshHostProfile,
    password: str,
    argv: Sequence[str],
    *,
    cwd: Optional[str] = None,
    cancel: Optional[threading.Event] = None,
    timeout_sec: Optional[float] = None,
    max_output_bytes: Optional[int] = None,
) -> tuple[int, str, str]:
    """Run argv on the remote host via Paramiko with cancel/timeout/output caps."""
    parts: list[str] = []
    if cwd:
        parts.extend(["cd", shlex.quote(cwd), "&&"])
    parts.extend(shlex.quote(part) for part in argv)
    remote = " ".join(parts)

    timeout, out_cap = resolve_ssh_job_limits(timeout_sec=timeout_sec, max_output_bytes=max_output_bytes)
    deadline = None if timeout <= 0 else time.monotonic() + timeout

    client, pinned = open_paramiko_ssh_client(profile, password=password)
    if pinned.host_key_fingerprint and pinned.host_key_fingerprint != profile.host_key_fingerprint:
        try:
            upsert_host_profile(pinned)
        except Exception:
            logging.debug("Could not persist SSH host key pin", exc_info=True)
    try:
        transport = client.get_transport()
        if transport is None:
            raise RuntimeError("SSH transport missing after connect")
        channel = transport.open_session()
        channel.settimeout(_POLL_INTERVAL_SEC)
        channel.exec_command(remote)
        out = bytearray()
        err = bytearray()
        out_trunc = False
        err_trunc = False
        while True:
            _raise_if_cancelled_or_timed_out(cancel, deadline, timeout, "exec")
            if channel.recv_ready():
                chunk = channel.recv(_RECV_CHUNK)
                out, out_trunc = _append_capped(out, chunk, out_cap, out_trunc)
            if channel.recv_stderr_ready():
                chunk = channel.recv_stderr(_RECV_CHUNK)
                err, err_trunc = _append_capped(err, chunk, out_cap, err_trunc)
            if channel.exit_status_ready():
                while channel.recv_ready():
                    chunk = channel.recv(_RECV_CHUNK)
                    out, out_trunc = _append_capped(out, chunk, out_cap, out_trunc)
                while channel.recv_stderr_ready():
                    chunk = channel.recv_stderr(_RECV_CHUNK)
                    err, err_trunc = _append_capped(err, chunk, out_cap, err_trunc)
                break
            time.sleep(_POLL_INTERVAL_SEC)
        code = int(channel.recv_exit_status())
        stdout = out.decode("utf-8", errors="replace")
        stderr = err.decode("utf-8", errors="replace")
        if out_trunc:
            stdout += "\n… [SSH stdout truncated]\n"
            logging.warning("SSH stdout truncated at %s bytes", out_cap)
        if err_trunc:
            stderr += "\n… [SSH stderr truncated]\n"
            logging.warning("SSH stderr truncated at %s bytes", out_cap)
        return code, stdout, stderr
    finally:
        client.close()


def _append_capped(
    buf: bytearray,
    chunk: bytes,
    limit: int,
    already_truncated: bool,
) -> tuple[bytearray, bool]:
    if not chunk:
        return buf, already_truncated
    if limit <= 0:
        buf.extend(chunk)
        return buf, already_truncated
    if already_truncated:
        return buf, True
    room = limit - len(buf)
    if room <= 0:
        return buf, True
    if len(chunk) <= room:
        buf.extend(chunk)
        return buf, False
    buf.extend(chunk[:room])
    return buf, True


def _raise_if_cancelled_or_timed_out(
    cancel: Optional[threading.Event],
    deadline: Optional[float],
    timeout: Optional[float],
    phase: str,
) -> None:
    if cancel is not None and cancel.is_set():
        raise SshRemoteJobCancelled(f"SSH {phase} cancelled")
    if deadline is not None and time.monotonic() > deadline:
        secs = timeout if timeout is not None else 0
        raise SshRemoteJobTimeout(f"SSH {phase} timed out after {secs}s")


def _call_on_gui_thread(fn: Callable[[], None]) -> None:
    """Best-effort marshal ``fn`` onto the Qt GUI thread; else call inline."""
    try:
        from ui.qt import QTimer

        mw = GlobalData().mainWindow
        if mw is not None:
            QTimer.singleShot(0, fn)
            return
    except Exception:
        logging.debug("SSH job GUI marshal unavailable; calling inline", exc_info=True)
    fn()


def _norm(path: str) -> str:
    text = (path or "").replace("\\", "/").strip()
    if not text:
        return "/"
    if not text.startswith("/"):
        text = "/" + text
    return posixpath.normpath(text)


__all__ = [
    "DEFAULT_SSH_JOB_TIMEOUT_SEC",
    "DEFAULT_SSH_MAX_OUTPUT_BYTES",
    "SYNC_CANCELLED",
    "SYNC_FAILED",
    "SYNC_LOCAL",
    "SYNC_SYNCED",
    "SYNC_SYNCING",
    "SshJobHandle",
    "SshRemoteJobCancelled",
    "SshRemoteJobTimeout",
    "after_save_upload_remote",
    "cancel_ssh_run",
    "cancel_ssh_upload",
    "clear_sync_state",
    "get_loaded_project_binding",
    "get_sync_state",
    "is_under_binding",
    "map_local_to_remote",
    "profile_from_binding",
    "resolve_ssh_job_limits",
    "run_remote_script",
    "schedule_remote_run",
    "schedule_remote_upload",
    "set_sync_state",
    "try_handle_ide_run",
]
