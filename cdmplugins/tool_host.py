# -*- coding: utf-8 -*-
#
# codimension - shared tool host resolution for lint/test drivers
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Ensure analysis tools are available in the project Python (R179).

When a ``-m`` tool module is missing from the project venv, offer to install
it there (preferred). Explicit IDE host is optional; silent IDE fallback is not.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Callable, Literal, Mapping

from cdmplugins.process_env import (
    python_module_available,
    resolve_tool_python_and_environment,
)

_LOG = logging.getLogger(__name__)

ToolHostChoice = Literal["install", "ide", "cancel"]

# Map ``python -m`` module → pip distribution name.
TOOL_PIP_PACKAGES: dict[str, str] = {
    "mypy": "mypy",
    "ruff": "ruff",
    "bandit": "bandit",
    "pytest": "pytest",
    "coverage": "coverage",
    "pip_audit": "pip-audit",
}


def pip_package_for_module(module: str) -> str:
    """Return the pip package name for a ``-m`` module."""
    name = (module or "").strip()
    if not name:
        return ""
    return TOOL_PIP_PACKAGES.get(name, name.replace("_", "-"))


def _prompt_tool_host_choice(
    parent,
    *,
    module: str,
    package: str,
    project_python: str,
    can_install: bool,
    ide_available: bool,
    mutable_error: str | None,
    choice_provider: Callable[..., ToolHostChoice] | None,
) -> ToolHostChoice:
    """Ask how to proceed when the tool module is missing from project Python."""
    if choice_provider is not None:
        return choice_provider(
            module=module,
            package=package,
            project_python=project_python,
            can_install=can_install,
            ide_available=ide_available,
            mutable_error=mutable_error,
        )

    if parent is None:
        return "cancel"

    from ui.qt import QMessageBox

    box = QMessageBox(parent)
    box.setWindowTitle("Missing analysis tool")
    box.setIcon(QMessageBox.Question)
    lines = [
        f"Python module '{module}' is not installed in the project environment:",
        project_python,
        "",
        "Proper checks should use the project venv.",
    ]
    if can_install:
        lines.append(f"Install '{package}' into the project venv?")
    elif mutable_error:
        lines.append(f"Cannot install into this interpreter: {mutable_error}")
    box.setText("\n".join(lines))

    install_btn = None
    if can_install:
        install_btn = box.addButton("Install into project", QMessageBox.AcceptRole)
    ide_btn = None
    if ide_available:
        ide_btn = box.addButton("Use IDE tools once", QMessageBox.ActionRole)
    cancel_btn = box.addButton("Cancel", QMessageBox.RejectRole)
    box.setDefaultButton(install_btn or ide_btn or cancel_btn)
    box.exec_()
    clicked = box.clickedButton()
    if install_btn is not None and clicked == install_btn:
        return "install"
    if ide_btn is not None and clicked == ide_btn:
        return "ide"
    return "cancel"


def _install_tool_package(
    project,
    package: str,
    parent,
    *,
    install_runner: Callable[[list[str], str | None, str | None], None] | None = None,
) -> None:
    """Install ``package`` into the mutable project Python (pip sync)."""
    from utils.venvbootstrap import (
        MODE_SYNC,
        buildPipInstallCommand,
        requireMutableProjectPython,
        runPipInstall,
    )

    python = requireMutableProjectPython(project)
    project_dir = project.getProjectDir() if project is not None else None
    cmd = buildPipInstallCommand(python, mode=MODE_SYNC, packages=[package])
    _LOG.info("Installing tool package %s via: %s", package, " ".join(cmd))

    if install_runner is not None:
        install_runner(cmd, project_dir, project_dir)
        return

    if parent is not None:
        from ui.venvprocess import run_pip_with_progress

        run_pip_with_progress(parent, cmd, cwd=project_dir, project_dir=project_dir)
        return

    runPipInstall(cmd, cwd=project_dir, project_dir=project_dir)


def ensure_tool_python_and_environment(
    project,
    encoding: str = "utf-8",
    overrides: Mapping[str, str] | None = None,
    *,
    module: str | None = None,
    parent=None,
    env_factory: Callable[[], Any] | None = None,
    choice_provider: Callable[..., ToolHostChoice] | None = None,
    install_runner: Callable[[list[str], str | None, str | None], None] | None = None,
) -> tuple[str, Any] | str:
    """Resolve tool host Python/env, offering install when the module is missing.

    Returns ``(python_path, process_env)`` on success, or an error message string.
    Headless callers (no ``parent`` / ``choice_provider``) get a soft error instead
    of mutating the venv.
    """
    python_path, process_env = resolve_tool_python_and_environment(
        project,
        encoding,
        overrides,
        env_factory=env_factory,
        module=module,
        use_ide_host=False,
    )
    if not module or python_module_available(python_path, module):
        return python_path, process_env

    package = pip_package_for_module(module)
    mutable_error: str | None = None
    can_install = False
    try:
        from utils.venvbootstrap import requireMutableProjectPython

        requireMutableProjectPython(project)
        can_install = bool(package)
    except RuntimeError as exc:
        mutable_error = str(exc)
        can_install = False

    ide_python = sys.executable
    ide_available = bool(ide_python) and ide_python != python_path and python_module_available(ide_python, module)

    choice = _prompt_tool_host_choice(
        parent,
        module=module,
        package=package,
        project_python=python_path,
        can_install=can_install,
        ide_available=ide_available,
        mutable_error=mutable_error,
        choice_provider=choice_provider,
    )

    if choice == "install":
        if not can_install:
            return mutable_error or (f"Cannot install '{package}' into the project Python.")
        try:
            from ui.venvprocess import ProcessCancelled
        except ImportError:
            ProcessCancelled = ()  # type: ignore[misc, assignment]

        try:
            _install_tool_package(
                project,
                package,
                parent,
                install_runner=install_runner,
            )
        except ProcessCancelled:
            return "Install cancelled"
        except Exception as exc:
            _LOG.exception("Tool package install failed for %s", package)
            return f"Failed to install '{package}': {exc}"

        python_path, process_env = resolve_tool_python_and_environment(
            project,
            encoding,
            overrides,
            env_factory=env_factory,
            module=module,
            use_ide_host=False,
        )
        if not python_module_available(python_path, module):
            return f"Installed '{package}' but module '{module}' is still not importable in {python_path}."
        return python_path, process_env

    if choice == "ide":
        if not ide_available:
            return (
                f"Python module '{module}' is not available in the IDE environment either. "
                f"Install it into the project venv (pip install {package}) or disable the plugin."
            )
        return resolve_tool_python_and_environment(
            project,
            encoding,
            overrides,
            env_factory=env_factory,
            module=module,
            use_ide_host=True,
        )

    return (
        f"Python module '{module}' is not installed in the project environment. "
        f"Install it (pip install {package}) into the project venv, "
        f"use VENV… / Update VENV, or disable the plugin."
    )
