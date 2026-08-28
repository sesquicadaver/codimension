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

"""Local ExecutionTarget adapter over utils.run argv builders (R122 / R187).

RunManager / ``getCwdCmdEnv`` call ``prepare_*`` for redirected IDE sessions.
``run`` / ``debug`` / ``profile`` execute synchronously by default (R187).
"""

from __future__ import annotations

import subprocess
from typing import Any, Optional

from core.execution import (
    ExecutionPlan,
    ExecutionRequest,
    ExecutionResult,
    ExecutionTarget,
    plan_to_prepare_result,
)

from .run import buildArgvToDebug, buildArgvToProfile, buildArgvToRun, resolveInterpreter
from .runparams import RunParameters


def _default_params() -> RunParameters:
    """Return fresh default run parameters (inherited interpreter, redirected)."""
    return RunParameters()


class LocalExecutionTarget:
    """ExecutionTarget that builds local argv via ``utils.run`` helpers.

    Use ``prepare_run`` / ``prepare_debug`` / ``prepare_profile`` for argv-only
    plans (IDE redirected sessions). ``run`` / ``debug`` / ``profile`` execute
    with ``subprocess.run`` by default (``wait=True``).
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
            raw: Any = self._params
            if hasattr(raw, "__setitem__"):
                raw["useInherited"] = False
                raw["customInterpreter"] = python
            else:
                merged = dict(raw)
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

    def prepare_run(self, request: ExecutionRequest) -> ExecutionPlan:
        """Return local run argv without executing."""
        argv = buildArgvToRun(
            request.script,
            list(request.args),
            self._params,
            request.tcp_port,
            request.procuuid,
        )
        return self._plan("run", argv, request)

    def prepare_debug(self, request: ExecutionRequest) -> ExecutionPlan:
        """Return local debug-client argv without executing."""
        port = request.tcp_port if request.tcp_port is not None else 0
        argv = buildArgvToDebug(
            request.script,
            list(request.args),
            self._params,
            port,
            request.procuuid,
        )
        return self._plan("debug", argv, request)

    def prepare_profile(self, request: ExecutionRequest) -> ExecutionPlan:
        """Return local profile argv without executing."""
        argv = buildArgvToProfile(
            request.script,
            list(request.args),
            self._params,
            request.tcp_port,
            request.procuuid,
        )
        return self._plan("profile", argv, request)

    def run(self, request: ExecutionRequest, *, wait: bool = True) -> ExecutionResult:
        """Execute a local run (default) or return a prepare-shaped result."""
        return self._finish(self.prepare_run(request), request, wait=wait)

    def debug(self, request: ExecutionRequest, *, wait: bool = True) -> ExecutionResult:
        """Execute a local debug session (default) or prepare-shaped result."""
        return self._finish(self.prepare_debug(request), request, wait=wait)

    def profile(self, request: ExecutionRequest, *, wait: bool = True) -> ExecutionResult:
        """Execute a local profile session (default) or prepare-shaped result."""
        return self._finish(self.prepare_profile(request), request, wait=wait)

    def _plan(self, mode: str, argv: list[str], request: ExecutionRequest) -> ExecutionPlan:
        meta: dict[str, str] = {"mode": mode, "backend": "local"}
        if request.cwd:
            meta["cwd"] = request.cwd
        return ExecutionPlan(mode=mode, argv=tuple(argv), metadata=meta)

    def _finish(self, plan: ExecutionPlan, request: ExecutionRequest, *, wait: bool) -> ExecutionResult:
        """Execute ``plan.argv`` or return prepare-only result when ``wait=False``."""
        if not wait:
            return plan_to_prepare_result(plan)

        env = None
        if request.env is not None:
            import os

            env = os.environ.copy()
            env.update(dict(request.env))
        completed = subprocess.run(
            list(plan.argv),
            cwd=request.cwd,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        return ExecutionResult(
            exit_code=int(completed.returncode),
            argv=plan.argv,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
            metadata=dict(plan.metadata),
        )


def local_execution_target(params: Optional[Any] = None, *, python: Optional[str] = None) -> ExecutionTarget:
    """Factory returning a typed ``ExecutionTarget`` for local runs."""
    return LocalExecutionTarget(params, python=python)
