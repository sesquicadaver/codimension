# -*- coding: utf-8 -*-
#
# codimension - graphics python two-way code editor and analyzer
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""SSH ExecutionTarget MVP (R124).

Runs Python over an injectable ``SSHTransport``. Contract tests use a fake
transport; ``SubprocessSSHTransport`` shells out to ``ssh`` for real hosts.

Sync strategy (MVP): the script path in ``ExecutionRequest`` is treated as a
**remote** path that already exists on the host. No automatic scp/rsync is
performed — document and verify per platform before relying on live SSH.
IDE TCP redirect debug clients are not wired; debug/profile use remote
``pdb`` / ``cProfile`` like the Docker MVP.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
from typing import Mapping, Optional, Protocol, Sequence, runtime_checkable

from core.execution import ExecutionRequest, ExecutionResult, ExecutionTarget


@runtime_checkable
class SSHTransport(Protocol):
    """Minimal remote command transport for SSHExecutionTarget."""

    def exec(
        self,
        argv: Sequence[str],
        *,
        cwd: Optional[str] = None,
        env: Optional[Mapping[str, str]] = None,
    ) -> tuple[int, str, str]:
        """Run ``argv`` on the remote side; return ``(exit, stdout, stderr)``."""


class FakeSSHTransport:
    """Recording transport for contract tests (no network)."""

    def __init__(self, *, exit_code: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.calls: list[tuple[tuple[str, ...], Optional[str], Optional[dict[str, str]]]] = []

    def exec(
        self,
        argv: Sequence[str],
        *,
        cwd: Optional[str] = None,
        env: Optional[Mapping[str, str]] = None,
    ) -> tuple[int, str, str]:
        env_copy = dict(env) if env is not None else None
        self.calls.append((tuple(argv), cwd, env_copy))
        return self.exit_code, self.stdout, self.stderr


class SubprocessSSHTransport:
    """Transport that invokes the system ``ssh`` client.

    Platform note: OpenSSH client layouts differ (ControlPath, IdentityFile,
    ProxyJump). This MVP is best-effort and **unverified** on Windows / exotic
    SSH wrappers — prefer FakeSSHTransport in CI.
    """

    def __init__(
        self,
        host: str,
        *,
        user: Optional[str] = None,
        port: int = 22,
        ssh_bin: str = "ssh",
        identity_file: Optional[str] = None,
        extra_ssh_args: Sequence[str] = (),
    ) -> None:
        if not host.strip():
            raise ValueError("host must be non-empty")
        self._host = host
        self._user = user
        self._port = int(port)
        self._ssh_bin = ssh_bin
        self._identity_file = identity_file
        self._extra_ssh_args = tuple(extra_ssh_args)

    @property
    def destination(self) -> str:
        """``user@host`` or ``host`` for ssh argv."""
        if self._user:
            return f"{self._user}@{self._host}"
        return self._host

    def build_ssh_argv(self, remote_command: str) -> list[str]:
        """Compose local ``ssh … destination -- remote_command`` argv."""
        argv = [self._ssh_bin, "-p", str(self._port)]
        if self._identity_file:
            argv.extend(["-i", self._identity_file])
        argv.extend(self._extra_ssh_args)
        argv.extend([self.destination, "--", remote_command])
        return argv

    def exec(
        self,
        argv: Sequence[str],
        *,
        cwd: Optional[str] = None,
        env: Optional[Mapping[str, str]] = None,
    ) -> tuple[int, str, str]:
        """Run argv remotely via a login shell fragment."""
        parts: list[str] = []
        if env:
            for key, value in env.items():
                parts.append(f"{shlex.quote(key)}={shlex.quote(value)}")
        if cwd:
            parts.append("cd")
            parts.append(shlex.quote(cwd))
            parts.append("&&")
        parts.extend(shlex.quote(part) for part in argv)
        remote = " ".join(parts)
        completed = subprocess.run(
            self.build_ssh_argv(remote),
            capture_output=True,
            text=True,
            check=False,
        )
        return int(completed.returncode), completed.stdout or "", completed.stderr or ""


def ssh_cli_available(ssh_bin: str = "ssh") -> bool:
    """Return True when an ssh client binary is on PATH (daemon not checked)."""
    return shutil.which(ssh_bin) is not None


class SSHExecutionTarget:
    """ExecutionTarget that executes via an ``SSHTransport``.

    By default methods only *prepare* the remote argv (``exit_code`` is
    ``None``). Pass ``wait=True`` to execute through the transport.
    """

    def __init__(
        self,
        transport: SSHTransport,
        *,
        python: str = "python3",
        host_label: str = "remote",
    ) -> None:
        """Bind transport and remote interpreter.

        Args:
            transport: Fake or subprocess SSH transport.
            python: Remote interpreter path/name.
            host_label: Label used in ``which_python`` / metadata.
        """
        self._transport = transport
        self._python = python
        self._host_label = host_label

    @property
    def transport(self) -> SSHTransport:
        """Bound SSH transport."""
        return self._transport

    def which_python(self) -> str:
        """Return a backend-qualified remote interpreter id."""
        return f"ssh:{self._host_label}:{self._python}"

    def run(self, request: ExecutionRequest, *, wait: bool = False) -> ExecutionResult:
        """Build (and optionally execute) a remote run argv."""
        inner = [self._python, request.script, *request.args]
        return self._finish("run", inner, request, wait=wait)

    def debug(self, request: ExecutionRequest, *, wait: bool = False) -> ExecutionResult:
        """MVP: remote ``python -m pdb`` (no IDE TCP redirect)."""
        inner = [self._python, "-m", "pdb", request.script, *request.args]
        return self._finish("debug", inner, request, wait=wait)

    def profile(self, request: ExecutionRequest, *, wait: bool = False) -> ExecutionResult:
        """MVP: remote ``python -m cProfile``."""
        outfile = request.profile_outfile or "codimension-profile.out"
        inner = [self._python, "-m", "cProfile", "-o", outfile, request.script, *request.args]
        return self._finish("profile", inner, request, wait=wait)

    def _finish(
        self,
        mode: str,
        inner_argv: Sequence[str],
        request: ExecutionRequest,
        *,
        wait: bool,
    ) -> ExecutionResult:
        """Attach metadata and optionally wait on the transport."""
        meta: dict[str, str] = {
            "mode": mode,
            "backend": "ssh",
            "host": self._host_label,
            "sync": "remote-path-assumed",
        }
        argv = tuple(inner_argv)
        if not wait:
            return ExecutionResult(exit_code=None, argv=argv, metadata=meta)

        code, stdout, stderr = self._transport.exec(
            inner_argv,
            cwd=request.cwd,
            env=request.env,
        )
        return ExecutionResult(
            exit_code=int(code),
            argv=argv,
            stdout=stdout,
            stderr=stderr,
            metadata=meta,
        )


def ssh_execution_target(
    transport: SSHTransport,
    *,
    python: str = "python3",
    host_label: str = "remote",
) -> ExecutionTarget:
    """Factory returning a typed ``ExecutionTarget`` for SSH runs."""
    return SSHExecutionTarget(transport, python=python, host_label=host_label)
