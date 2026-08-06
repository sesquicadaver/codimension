# -*- coding: utf-8 -*-
#
# codimension - shared QProcess environment for tool drivers
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Build a QProcessEnvironment that inherits the system environment (T030/R112)."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Callable, Mapping, Optional

if TYPE_CHECKING:
    from utils.analysis_environment import AnalysisEnvironment


def _prepend_pythonpath(env: Any, prefix: str) -> None:
    """Prepend ``prefix`` to PYTHONPATH on a QProcessEnvironment-like object."""
    existing = ""
    if hasattr(env, "value"):
        existing = env.value("PYTHONPATH", "") or ""
    elif isinstance(env, Mapping):
        existing = str(env.get("PYTHONPATH", "") or "")
    merged = prefix if not existing else prefix + os.pathsep + existing
    if hasattr(env, "insert"):
        env.insert("PYTHONPATH", merged)
    elif isinstance(env, dict):
        env["PYTHONPATH"] = merged


def _apply_analysis_env(env: Any, analysis_env: AnalysisEnvironment) -> None:
    """Apply AnalysisEnvironment-derived overrides onto ``env``."""
    from utils.analysis_environment import tool_environ_overrides

    overrides = tool_environ_overrides(analysis_env)
    pythonpath = overrides.pop("PYTHONPATH", None)
    if pythonpath:
        _prepend_pythonpath(env, pythonpath)
    for key, value in overrides.items():
        if hasattr(env, "insert"):
            env.insert(str(key), str(value))
        elif isinstance(env, dict):
            env[str(key)] = str(value)


def build_tool_process_environment(
    encoding: str = "utf-8",
    overrides: Mapping[str, str] | None = None,
    *,
    analysis_env: Optional[AnalysisEnvironment] = None,
    env_factory: Callable[[], Any] | None = None,
) -> Any:
    """Return a process environment based on the parent process.

    Uses ``QProcessEnvironment.systemEnvironment()`` unless ``env_factory`` is
    provided (tests). Always sets ``PYTHONIOENCODING``.

    When ``analysis_env`` is provided (R112), prepends site-packages to
    ``PYTHONPATH`` and sets ``VIRTUAL_ENV`` when the interpreter is a venv.
    """
    if env_factory is not None:
        env = env_factory()
    else:
        from ui.qt import QProcessEnvironment

        env = QProcessEnvironment.systemEnvironment()
    env.insert("PYTHONIOENCODING", encoding or "utf-8")
    if analysis_env is not None:
        _apply_analysis_env(env, analysis_env)
    if overrides:
        for key, value in overrides.items():
            env.insert(str(key), str(value))
    return env


def resolve_tool_python_and_environment(
    project,
    encoding: str = "utf-8",
    overrides: Mapping[str, str] | None = None,
    *,
    env_factory: Callable[[], Any] | None = None,
) -> tuple[str, Any]:
    """Return ``(python_path, QProcessEnvironment)`` from project analysis env.

    Uses ``buildAnalysisEnvironment(..., for_tools=True)`` so broken configured
    interpreters fall back the same way as ``getEffectiveProjectPython``.
    """
    from utils.venvbootstrap import buildAnalysisEnvironment

    analysis_env = buildAnalysisEnvironment(project, for_tools=True)
    process_env = build_tool_process_environment(
        encoding,
        overrides,
        analysis_env=analysis_env,
        env_factory=env_factory,
    )
    return analysis_env.python_path, process_env
