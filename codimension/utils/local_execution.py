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

"""Local ExecutionTarget adapter over utils.run argv builders (R122).

RunManager / ``getCwdCmdEnv`` prepare process argv through this target so
local runs share the same contract as future Docker/SSH/K8s backends.
"""

from __future__ import annotations

import subprocess
from typing import Any, Optional

from core.execution import ExecutionRequest, ExecutionResult, ExecutionTarget

from .run import buildArgvToDebug, buildArgvToProfile, buildArgvToRun, resolveInterpreter
from .runparams import RunParameters


def _default_params() -> RunParameters:
    """Return fresh default run parameters (inherited interpreter, redirected)."""
    return RunParameters()


class LocalExecutionTarget:
    """ExecutionTarget that builds local argv via ``utils.run`` helpers.

    By default methods only *prepare* argv (``exit_code`` is ``None``) so the
    IDE can start long-lived redirected sessions. Pass ``wait=True`` to run
    synchronously with ``subprocess.run`` (headless / tests).
    """

    def __init__(
        self,
        params: Optional[Any] = None,
        *,
        python: Optional[str] = None,
    ) -> None:
        """Bind run parameters and optional forced interpreter path.

        Args:
            params: ``RunParameters`` or mapping with the same keys.
            python: When set, forces ``customInterpreter`` (ignores inherited).
        """
        self._params = params if params is not None else _default_params()
        if python:
            # Force a concrete interpreter without mutating caller state deeply.
            if hasattr(self._params, "__setitem__"):
                self._params["useInherited"] = False
                self._params["customInterpreter"] = python
            else:
                merged = dict(self._params)
                merged["useInherited"] = False
                merged["customInterpreter"] = python
                self._params = merged

    @property
    def params(self) -> Any:
        """Bound run parameters object/mapping."""
        return self._params

    def which_python(self) -> str:
        """Return the interpreter used for local argv construction."""
        return resolveInterpreter(self._params)

    def run(self, request: ExecutionRequest, *, wait: bool = False) -> ExecutionResult:
        """Build (and optionally execute) a local run argv."""
        argv = buildArgvToRun(
            request.script,
            list(request.args),
            self._params,
            request.tcp_port,
            request.procuuid,
        )
        return self._finish("run", argv, request, wait=wait)

    def debug(self, request: ExecutionRequest, *, wait: bool = False) -> ExecutionResult:
        """Build (and optionally execute) a local debug-client argv."""
        port = request.tcp_port if request.tcp_port is not None else 0
        argv = buildArgvToDebug(
            request.script,
            list(request.args),
            self._params,
            port,
            request.procuuid,
        )
        return self._finish("debug", argv, request, wait=wait)

    def profile(self, request: ExecutionRequest, *, wait: bool = False) -> ExecutionResult:
        """Build (and optionally execute) a local profile argv."""
        argv = buildArgvToProfile(
            request.script,
            list(request.args),
            self._params,
            request.tcp_port,
            request.procuuid,
        )
        return self._finish("profile", argv, request, wait=wait)

    def _finish(
        self,
        mode: str,
        argv: list[str],
        request: ExecutionRequest,
        *,
        wait: bool,
    ) -> ExecutionResult:
        """Attach metadata and optionally wait on a subprocess."""
        meta: dict[str, str] = {"mode": mode, "backend": "local"}
        if request.cwd:
            meta["cwd"] = request.cwd
        if not wait:
            return ExecutionResult(exit_code=None, argv=tuple(argv), metadata=meta)

        env = None
        if request.env is not None:
            import os

            env = os.environ.copy()
            env.update(dict(request.env))
        completed = subprocess.run(
            argv,
            cwd=request.cwd,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        return ExecutionResult(
            exit_code=int(completed.returncode),
            argv=tuple(argv),
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
            metadata=meta,
        )


def local_execution_target(params: Optional[Any] = None, *, python: Optional[str] = None) -> ExecutionTarget:
    """Factory returning a typed ``ExecutionTarget`` for local runs."""
    return LocalExecutionTarget(params, python=python)
