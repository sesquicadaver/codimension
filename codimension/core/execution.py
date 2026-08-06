# -*- coding: utf-8 -*-
#
# codimension - headless execution target contract (R121)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""ExecutionTarget protocol — run / debug / profile / which_python (R121).

Local (R122), Docker (R123), SSH (R124), and Kubernetes (R125) backends will
implement this contract. The protocol is Qt-free and lives in ``core`` so
headless tooling can depend on it without pulling ``utils.run`` / RunManager.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping, Optional, Protocol, Sequence, runtime_checkable


@dataclass(frozen=True)
class ExecutionRequest:
    """Immutable parameters for a single run/debug/profile invocation.

    Attributes:
        script: Path to the Python script (local path or backend-specific URI).
        args: Extra argv after the script.
        cwd: Working directory when known; ``None`` lets the backend decide.
        env: Optional environment overrides (merged by the backend).
        tcp_port: IDE TCP server port for redirected debug/run clients.
        procuuid: Process UUID used by redirected clients / profile outfiles.
        profile_outfile: Optional cProfile output path (profile mode).
    """

    script: str
    args: tuple[str, ...] = ()
    cwd: Optional[str] = None
    env: Optional[Mapping[str, str]] = None
    tcp_port: Optional[int] = None
    procuuid: Optional[str] = None
    profile_outfile: Optional[str] = None

    def __post_init__(self) -> None:
        """Normalize ``args`` to a tuple for frozen safety."""
        if not isinstance(self.args, tuple):
            object.__setattr__(self, "args", tuple(self.args))


@dataclass(frozen=True)
class ExecutionResult:
    """Outcome of an ExecutionTarget invocation.

    For asynchronous / long-lived backends (future R122+), ``exit_code`` may be
    ``None`` while a session is still running; MVP fakes use an int.
    """

    exit_code: Optional[int]
    argv: tuple[str, ...] = ()
    stdout: str = ""
    stderr: str = ""
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Normalize argv / metadata to immutable containers."""
        if not isinstance(self.argv, tuple):
            object.__setattr__(self, "argv", tuple(self.argv))
        meta = dict(self.metadata) if self.metadata else {}
        object.__setattr__(self, "metadata", MappingProxyType(meta))


@runtime_checkable
class ExecutionTarget(Protocol):
    """Backend that can run, debug, and profile Python code.

    Implementations must be substitutable for local process, Docker, SSH, and
    Kubernetes runners without UI coupling.
    """

    def which_python(self) -> str:
        """Return the interpreter path (or backend id) used for executions."""

    def run(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute ``request.script`` as a normal run."""

    def debug(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute under the debugger client / remote debug protocol."""

    def profile(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute under the profiler (cProfile or redirected profile client)."""


def assert_execution_target(obj: object) -> ExecutionTarget:
    """Raise ``TypeError`` if ``obj`` does not satisfy ``ExecutionTarget``."""
    if not isinstance(obj, ExecutionTarget):
        raise TypeError(f"object is not an ExecutionTarget: {type(obj)!r}")
    return obj  # type: ignore[return-value]


def build_request(
    script: str,
    args: Sequence[str] = (),
    *,
    cwd: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
    tcp_port: Optional[int] = None,
    procuuid: Optional[str] = None,
    profile_outfile: Optional[str] = None,
) -> ExecutionRequest:
    """Convenience constructor that accepts any sequence for ``args``."""
    return ExecutionRequest(
        script=script,
        args=tuple(args),
        cwd=cwd,
        env=env,
        tcp_port=tcp_port,
        procuuid=procuuid,
        profile_outfile=profile_outfile,
    )
