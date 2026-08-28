# -*- coding: utf-8 -*-
#
# codimension - SSH IDE debug session (R198)
# Copyright (C) 2026  Codimension Team
# The license is described in the LICENSE file at the root directory.
#

"""SSH remote IDE debug: reverse tunnel + remote ``client_cdm_dbg`` (R198).

Local IDE listens on ``127.0.0.1:<port>``. The debuggee runs on the SSH host and
connects to ``127.0.0.1:<port>`` there; a reverse port-forward bridges the two.
Pathnames in the debug protocol are remapped remote ↔ local cache via the
project ``binding.json``.
"""

from __future__ import annotations

import logging
import os
import posixpath
import socket
import threading
from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol, Sequence

from utils.run import _debuggerClientPath
from utils.ssh_project_runtime import (
    map_local_to_remote,
    profile_from_binding,
    resolve_ssh_job_limits,
)
from utils.ssh_remote import (
    RemoteProjectBinding,
    load_ssh_password,
    open_paramiko_ssh_client,
    require_paramiko,
    upload_file,
)

REMOTE_CLIENT_DIR = ".codimension-dbg-client"
_CLIENT_SCRIPTS = (
    "client_cdm_dbg.py",
    "clientbase_cdm_dbg.py",
    "base_cdm_dbg.py",
    "bp_wp_cdm_dbg.py",
    "cdm_dbg_utils.py",
    "protocol_cdm_dbg.py",
    "asyncfile_cdm_dbg.py",
    "outredir_cdm_dbg.py",
    "threadextension_cdm_dbg.py",
    "threadutils_cdm_dbg.py",
    "variables_cdm_dbg.py",
    "getpass.py",
    "__init__.py",
)

_path_mapper: Optional[Callable[[str], str]] = None
_path_mapper_lock = threading.Lock()


@dataclass(frozen=True)
class ReverseTunnelSpec:
    """Reverse forward: remote ``127.0.0.1:remote_port`` → local host:port."""

    remote_port: int
    local_port: int
    local_host: str = "127.0.0.1"


@dataclass
class SshIdeDebugPlan:
    """Prepared SSH IDE debug session (argv + uploads + tunnel)."""

    local_script: str
    remote_script: str
    remote_client_root: str
    remote_client_script: str
    argv: tuple[str, ...]
    tunnel: ReverseTunnelSpec
    procuuid: str
    upload_pairs: tuple[tuple[str, str], ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)


class ReverseTunnel(Protocol):
    """Minimal reverse-forward lifecycle for IDE debug."""

    def open(self, spec: ReverseTunnelSpec) -> None:
        """Start forwarding."""

    def close(self) -> None:
        """Stop forwarding."""


class FakeReverseTunnel:
    """Recording tunnel for contract tests (no network)."""

    def __init__(self) -> None:
        self.opened: list[ReverseTunnelSpec] = []
        self.closed = 0

    def open(self, spec: ReverseTunnelSpec) -> None:
        self.opened.append(spec)

    def close(self) -> None:
        self.closed += 1


class ParamikoReverseTunnel:
    """Paramiko reverse port-forward (remote listen → local IDE TCP)."""

    def __init__(self, ssh_client) -> None:
        self._client = ssh_client
        self._transport = None
        self._spec: Optional[ReverseTunnelSpec] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def open(self, spec: ReverseTunnelSpec) -> None:
        """Request remote port forward and bridge accepted channels locally."""
        self._spec = spec
        self._transport = self._client.get_transport()
        if self._transport is None:
            raise RuntimeError("SSH transport is not available for reverse forward")
        self._transport.request_port_forward("", int(spec.remote_port))
        self._stop.clear()
        self._thread = threading.Thread(target=self._serve, name="ssh-rforward", daemon=True)
        self._thread.start()

    def close(self) -> None:
        """Cancel forward and stop the acceptor thread."""
        self._stop.set()
        try:
            if self._transport is not None and self._spec is not None:
                self._transport.cancel_port_forward("", int(self._spec.remote_port))
        except Exception:
            logging.debug("cancel_port_forward failed", exc_info=True)
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _serve(self) -> None:
        assert self._transport is not None and self._spec is not None
        spec = self._spec
        while not self._stop.is_set():
            chan = self._transport.accept(0.5)
            if chan is None:
                continue
            threading.Thread(
                target=self._bridge,
                args=(chan, spec.local_host, spec.local_port),
                daemon=True,
            ).start()

    @staticmethod
    def _bridge(chan, local_host: str, local_port: int) -> None:
        try:
            sock = socket.create_connection((local_host, int(local_port)), timeout=10.0)
        except OSError:
            try:
                chan.close()
            except Exception:
                pass
            return

        def _pump(src, dst) -> None:
            try:
                while True:
                    data = src.recv(65536)
                    if not data:
                        break
                    dst.sendall(data)
            except Exception:
                pass
            finally:
                try:
                    src.close()
                except Exception:
                    pass
                try:
                    dst.close()
                except Exception:
                    pass

        t1 = threading.Thread(target=_pump, args=(chan, sock), daemon=True)
        t2 = threading.Thread(target=_pump, args=(sock, chan), daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()


def set_ssh_debug_path_mapper(mapper: Optional[Callable[[str], str]]) -> None:
    """Install or clear the active remote→local filename mapper (IDE session)."""
    global _path_mapper
    with _path_mapper_lock:
        _path_mapper = mapper


def remap_debug_filename(filename: str) -> str:
    """Map a debug protocol filename to the local cache path when possible."""
    with _path_mapper_lock:
        mapper = _path_mapper
    if mapper is None or not filename:
        return filename
    try:
        return mapper(filename)
    except Exception:
        return filename


def remap_debug_stack(stack: list) -> list:
    """Rewrite stack frame filenames through :func:`remap_debug_filename`."""
    if not stack:
        return stack
    out = []
    for entry in stack:
        if isinstance(entry, (list, tuple)) and entry:
            frame = list(entry)
            frame[0] = remap_debug_filename(str(frame[0]))
            out.append(frame if isinstance(entry, list) else tuple(frame))
        else:
            out.append(entry)
    return out


def map_remote_to_local(binding: RemoteProjectBinding, remote_path: str) -> str:
    """Map a remote POSIX path under ``remote_root`` to the local cache path."""
    remote = remote_path.replace("\\", "/")
    root = binding.remote_root.rstrip("/")
    if remote == root or remote == root + "/":
        return str(os.path.realpath(binding.local_root))
    prefix = root + "/"
    if not remote.startswith(prefix):
        raise ValueError(f"remote path outside project root: {remote_path}")
    rel = remote[len(prefix) :]
    return str(os.path.realpath(os.path.join(binding.local_root, *rel.split("/"))))


def make_binding_path_mapper(binding: RemoteProjectBinding) -> Callable[[str], str]:
    """Return a mapper that rewrites remote script paths to the local cache."""

    def _map(filename: str) -> str:
        try:
            return map_remote_to_local(binding, filename)
        except ValueError:
            return filename

    return _map


def list_debugger_client_uploads(remote_client_root: str) -> list[tuple[str, str]]:
    """Return ``(local_path, remote_path)`` pairs for the debug client package."""
    pairs: list[tuple[str, str]] = []
    for name in _CLIENT_SCRIPTS:
        local = _debuggerClientPath(name)
        if not os.path.isfile(local):
            continue
        pairs.append((local, posixpath.join(remote_client_root, name)))
    return pairs


def build_ssh_ide_debug_argv(
    *,
    remote_python: str,
    remote_client_script: str,
    remote_script: str,
    arguments: Sequence[str],
    tcp_port: int,
    procuuid: str,
    report_exceptions: bool = True,
    trace_interpreter: bool = False,
    redirected: bool = True,
) -> list[str]:
    """Build remote argv for ``client_cdm_dbg`` connecting via reverse tunnel."""
    parts = [
        remote_python,
        remote_client_script,
        "--host",
        "127.0.0.1",
        "--port",
        str(int(tcp_port)),
        "--procuuid",
        str(procuuid),
        "--encoding",
        "utf-8",
    ]
    if not report_exceptions:
        parts.append("--no-exc-report")
    if trace_interpreter:
        parts.append("--trace-python")
    if not redirected:
        parts.append("--no-redirect")
    parts.extend(["--", remote_script, *list(arguments)])
    return parts


def prepare_ssh_ide_debug_plan(
    binding: RemoteProjectBinding,
    local_script: str,
    *,
    tcp_port: int,
    procuuid: str,
    arguments: Sequence[str] = (),
    remote_python: str = "python3",
    report_exceptions: bool = True,
    trace_interpreter: bool = False,
    redirected: bool = True,
) -> SshIdeDebugPlan:
    """Build upload list, tunnel spec, and remote debug argv (no I/O)."""
    remote_script = map_local_to_remote(binding, local_script)
    remote_client_root = posixpath.join(binding.remote_root.rstrip("/"), REMOTE_CLIENT_DIR)
    remote_client_script = posixpath.join(remote_client_root, "client_cdm_dbg.py")
    uploads = tuple(list_debugger_client_uploads(remote_client_root))
    uploads = uploads + ((os.path.realpath(local_script), remote_script),)
    tunnel = ReverseTunnelSpec(remote_port=int(tcp_port), local_port=int(tcp_port))
    argv = tuple(
        build_ssh_ide_debug_argv(
            remote_python=remote_python,
            remote_client_script=remote_client_script,
            remote_script=remote_script,
            arguments=arguments,
            tcp_port=tcp_port,
            procuuid=procuuid,
            report_exceptions=report_exceptions,
            trace_interpreter=trace_interpreter,
            redirected=redirected,
        )
    )
    return SshIdeDebugPlan(
        local_script=os.path.realpath(local_script),
        remote_script=remote_script,
        remote_client_root=remote_client_root,
        remote_client_script=remote_client_script,
        argv=argv,
        tunnel=tunnel,
        procuuid=str(procuuid),
        upload_pairs=uploads,
        metadata={
            "backend": "ssh-ide-debug",
            "protocol": "client_cdm_dbg",
            "tunnel": "reverse",
        },
    )


def start_ssh_ide_debug_session(
    binding: RemoteProjectBinding,
    local_script: str,
    proc_wrapper,
    tcp_port: int,
    *,
    arguments: Optional[Sequence[str]] = None,
    tunnel_factory: Optional[Callable[[object], ReverseTunnel]] = None,
    on_finished: Optional[Callable[[int], None]] = None,
) -> SshIdeDebugPlan:
    """Upload client + script, open reverse tunnel, exec remote debuggee.

    ``proc_wrapper`` is a ``RemoteProcessWrapper`` (not started locally). When
    the remote process ends, ``proc_wrapper.sigFinished`` is emitted.
    """
    require_paramiko()
    from utils.diskvaluesrelay import getRunParameters
    from utils.settings import Settings
    from utils.ssh_remote import connect_paramiko_sftp

    params = getRunParameters(local_script)
    if arguments is None:
        import shlex

        raw = params.get("arguments") or ""
        arguments = shlex.split(raw) if raw else []
    dbg = Settings().getDebuggerSettings()
    plan = prepare_ssh_ide_debug_plan(
        binding,
        local_script,
        tcp_port=tcp_port,
        procuuid=proc_wrapper.procuuid,
        arguments=arguments,
        report_exceptions=bool(dbg.reportExceptions),
        trace_interpreter=bool(dbg.traceInterpreter),
        redirected=bool(params.get("redirected", True)),
    )
    set_ssh_debug_path_mapper(make_binding_path_mapper(binding))

    profile = profile_from_binding(binding)
    password = load_ssh_password(profile.id) if profile.auth == "password" else ""
    timeout, _cap = resolve_ssh_job_limits()

    def _worker() -> None:
        exit_code = -1
        client = None
        tunnel: Optional[ReverseTunnel] = None
        try:
            # Upload via SFTP session (closes its own client when done).
            sftp = connect_paramiko_sftp(profile, password=password)
            try:
                for local_path, remote_path in plan.upload_pairs:
                    parent = posixpath.dirname(remote_path)
                    if parent and parent != "/":
                        sftp.makedirs(parent)
                    upload_file(sftp, local_path, remote_path)
            finally:
                sftp.close()

            client, _pinned = open_paramiko_ssh_client(profile, password=password)
            factory = tunnel_factory or (lambda c: ParamikoReverseTunnel(c))
            tunnel = factory(client)
            tunnel.open(plan.tunnel)
            remote_cwd = posixpath.dirname(plan.remote_script) or binding.remote_root
            exit_code = _exec_argv(client, plan.argv, cwd=remote_cwd, timeout_sec=timeout or 0)
        except Exception as exc:
            logging.error("SSH IDE debug failed: %s", exc)
            exit_code = -1
        finally:
            if tunnel is not None:
                try:
                    tunnel.close()
                except Exception:
                    logging.debug("SSH reverse tunnel close failed", exc_info=True)
            if client is not None:
                try:
                    client.close()
                except Exception:
                    logging.debug("SSH client close failed", exc_info=True)
            set_ssh_debug_path_mapper(None)
            try:
                proc_wrapper.sigFinished.emit(proc_wrapper.procuuid, int(exit_code))
            except Exception:
                logging.debug("sigFinished emit failed", exc_info=True)
            if on_finished is not None:
                on_finished(int(exit_code))

    thread = threading.Thread(target=_worker, name="ssh-ide-debug", daemon=True)
    thread.start()
    return plan


def _exec_argv(client, argv: Sequence[str], *, cwd: str, timeout_sec: float) -> int:
    """Run argv on the remote host; return exit code."""
    import shlex

    cmd = " ".join(shlex.quote(part) for part in argv)
    if cwd:
        cmd = f"cd {shlex.quote(cwd)} && {cmd}"
    transport = client.get_transport()
    if transport is None:
        raise RuntimeError("SSH transport missing")
    channel = transport.open_session()
    if timeout_sec > 0:
        channel.settimeout(float(timeout_sec))
    channel.exec_command(cmd)
    while True:
        if channel.recv_ready():
            channel.recv(65536)
        if channel.recv_stderr_ready():
            channel.recv_stderr(65536)
        if channel.exit_status_ready():
            break
    return int(channel.recv_exit_status())
