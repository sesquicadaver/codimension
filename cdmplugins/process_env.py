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

"""Build a QProcessEnvironment that inherits the system environment (T030/R112/R178)."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from typing import TYPE_CHECKING, Any, Callable, Mapping, Optional, Sequence

if TYPE_CHECKING:
    from utils.analysis_environment import AnalysisEnvironment

_LOG = logging.getLogger(__name__)
_MODULE_PROBE_TIMEOUT_SEC = 8.0


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


def module_from_python_args(args: Sequence[str] | None) -> str | None:
    """Return ``-m`` module name from a Python argv list, or ``None``."""
    if not args or len(args) < 2:
        return None
    if args[0] != "-m":
        return None
    name = (args[1] or "").strip()
    return name or None


def python_module_available(
    python_path: str,
    module: str,
    *,
    timeout: float = _MODULE_PROBE_TIMEOUT_SEC,
) -> bool:
    """True if ``python_path -c 'import module'`` succeeds."""
    if not python_path or not module:
        return False
    # Only allow simple module names (no path injection).
    if not module.replace("_", "").replace(".", "").isalnum():
        return False
    try:
        completed = subprocess.run(
            [python_path, "-c", f"import {module}"],
            check=False,
            capture_output=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def resolve_tool_python_and_environment(
    project,
    encoding: str = "utf-8",
    overrides: Mapping[str, str] | None = None,
    *,
    env_factory: Callable[[], Any] | None = None,
    module: str | None = None,
) -> tuple[str, Any]:
    """Return ``(python_path, QProcessEnvironment)`` from project analysis env.

    Uses ``buildAnalysisEnvironment(..., for_tools=True)`` so broken configured
    interpreters fall back the same way as ``getEffectiveProjectPython``.

    When ``module`` is set (R178) and that import is missing in the project
    Python, falls back to the IDE ``sys.executable`` if the module is available
    there. Project ``site-packages`` stay on ``PYTHONPATH`` so analysis still
    sees project packages.
    """
    from utils.analysis_environment import AnalysisEnvironment
    from utils.venvbootstrap import buildAnalysisEnvironment

    analysis_env = buildAnalysisEnvironment(project, for_tools=True)
    python_path = analysis_env.python_path

    if module and not python_module_available(python_path, module):
        ide_python = sys.executable
        if ide_python != python_path and python_module_available(ide_python, module):
            _LOG.info(
                "Tool module %s not in project Python (%s); using IDE Python (%s)",
                module,
                python_path,
                ide_python,
            )
            # Keep project site-packages for import/type resolution; host the tool in IDE.
            analysis_env = AnalysisEnvironment(
                python_path=ide_python,
                source_kind=analysis_env.source_kind,
                site_packages_roots=analysis_env.site_packages_roots,
                project_id=analysis_env.project_id,
            )
            python_path = ide_python
        else:
            _LOG.warning(
                "Tool module %s is not installed in project Python (%s) or IDE Python (%s)",
                module,
                python_path,
                ide_python,
            )

    process_env = build_tool_process_environment(
        encoding,
        overrides,
        analysis_env=analysis_env,
        env_factory=env_factory,
    )
    return python_path, process_env
