# -*- coding: utf-8 -*-
"""Project venv create/attach/update helpers (T140)."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .venvutils import resolveVenvToPython

_LOG = logging.getLogger(__name__)

ROOT_VENV_NAMES = (".venv", "venv", "env")
MODE_UPGRADE = "upgrade"
MODE_SYNC = "sync"
MODE_RECREATE = "recreate"

# Session overlay lives here so helpers work without constructing GlobalData.
_SESSION_PYTHON = ""


def getSessionPythonInterpreter() -> str:
    """Return session-only interpreter overlay (may be empty)."""
    return _SESSION_PYTHON


def setSessionPythonInterpreter(path: str | None) -> None:
    """Set or clear session-only interpreter overlay."""
    global _SESSION_PYTHON
    _SESSION_PYTHON = (path or "").strip()
    try:
        from . import globals as globals_mod

        if globals_mod._globals_singleton is not None:
            globals_mod._globals_singleton.sessionPythonInterpreter = _SESSION_PYTHON
    except Exception:
        pass


def clearSessionPythonInterpreter() -> None:
    """Clear session overlay (project unload / after save)."""
    setSessionPythonInterpreter("")


def _resolveConfigured(project, interp: str) -> str:
    """Resolve configured interpreter path to an executable."""
    if not os.path.isabs(interp):
        project_dir = project.getProjectDir()
        if project_dir:
            interp = os.path.normpath(os.path.join(project_dir, interp))
    if os.path.isfile(interp) and os.access(interp, os.X_OK):
        return os.path.abspath(interp)
    venv_python = resolveVenvToPython(interp)
    if venv_python:
        return venv_python
    return sys.executable


def getEffectiveProjectPython(project) -> str:
    """Resolve project Python: props → session overlay → auto-detect → IDE."""
    if project is None or not project.isLoaded():
        return sys.executable

    interp = project.props.get("pythoninterpreter", "").strip()
    if interp:
        return _resolveConfigured(project, interp)

    session = getSessionPythonInterpreter()
    if session:
        if os.path.isfile(session) and os.access(session, os.X_OK):
            return os.path.abspath(session)
        venv_python = resolveVenvToPython(session)
        if venv_python:
            return venv_python

    project_dir = project.getProjectDir()
    if project_dir:
        for venv_name in ROOT_VENV_NAMES:
            venv_path = os.path.join(project_dir, venv_name)
            venv_python = resolveVenvToPython(venv_path)
            if venv_python:
                return venv_python
    return sys.executable


def isPythonInterpreterConfigured(project) -> bool:
    """True when ``pythoninterpreter`` project prop is non-empty."""
    if project is None or not project.isLoaded():
        return False
    return bool(project.props.get("pythoninterpreter", "").strip())


def venvSetupActionEnabled(project) -> bool:
    """VENV… menu: project loaded and interpreter prop empty."""
    return bool(project and project.isLoaded() and not isPythonInterpreterConfigured(project))


def venvUpdateActionEnabled(project) -> bool:
    """Update VENV…: configured prop or session overlay."""
    if project is None or not project.isLoaded():
        return False
    if isPythonInterpreterConfigured(project):
        return True
    return bool(getSessionPythonInterpreter())


def discoverRootVenvCandidates(project_dir: str) -> list[str]:
    """Return absolute root venv dirs that resolve to a python executable."""
    if not project_dir or not os.path.isdir(project_dir):
        return []
    found: list[str] = []
    for name in ROOT_VENV_NAMES:
        path = os.path.abspath(os.path.join(project_dir, name))
        if resolveVenvToPython(path):
            found.append(path)
    return found


def venvDirFromPython(python_path: str) -> str | None:
    """Best-effort venv root from ``.../bin/python`` or ``.../Scripts/python.exe``."""
    if not python_path:
        return None
    bin_dir = os.path.dirname(os.path.abspath(python_path))
    if os.path.basename(bin_dir) in ("bin", "Scripts"):
        return os.path.dirname(bin_dir)
    return None


def isPathInsideProject(venv_path: str, project_dir: str) -> bool:
    """True if ``venv_path`` is under ``project_dir`` (realpath prefix)."""
    try:
        venv_real = os.path.realpath(venv_path)
        proj_real = os.path.realpath(project_dir)
        return venv_real == proj_real or venv_real.startswith(proj_real + os.sep)
    except Exception:
        return False


def createVenv(base_python: str, venv_dir: str) -> str:
    """Create a venv; return path to the new python executable.

    Raises ``RuntimeError`` on failure.
    """
    base_python = base_python or sys.executable
    venv_dir = os.path.abspath(venv_dir)
    os.makedirs(os.path.dirname(venv_dir) or ".", exist_ok=True)
    cmd = [base_python, "-m", "venv", venv_dir]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"venv create failed: {exc.stderr or exc}") from exc
    python = resolveVenvToPython(venv_dir)
    if not python:
        raise RuntimeError(f"venv created but python not found under {venv_dir}")
    return python


def buildPipInstallCommand(
    venv_python: str,
    *,
    mode: str,
    requirement_files: list[str] | None = None,
    packages: list[str] | None = None,
    install_project: bool = False,
    project_dir: str | None = None,
) -> list[str]:
    """Build ``python -m pip install …`` argv (no network execution)."""
    if mode not in (MODE_UPGRADE, MODE_SYNC, MODE_RECREATE):
        raise ValueError(f"unknown pip mode: {mode}")
    cmd = [venv_python, "-m", "pip", "install"]
    if mode == MODE_UPGRADE:
        cmd.append("--upgrade")
    for req in requirement_files or []:
        cmd.extend(["-r", req])
    if install_project:
        cmd.append(project_dir or ".")
    for pkg in packages or []:
        if pkg:
            cmd.append(pkg)
    return cmd


def runPipInstall(cmd: list[str], *, cwd: str | None = None) -> None:
    """Execute pip install command; raise RuntimeError on failure."""
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, cwd=cwd)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"pip install failed: {exc.stderr or exc}") from exc


def recreateVenv(
    base_python: str,
    venv_dir: str,
    project_dir: str,
    *,
    requirement_files: list[str] | None = None,
    packages: list[str] | None = None,
    install_project: bool = False,
    runner_create=None,
    runner_pip=None,
    runner_rmtree=None,
) -> str:
    """Delete (if exists), create venv, sync-install selected sources.

    Refuses paths outside ``project_dir``. Returns new python path.
    """
    venv_dir = os.path.abspath(venv_dir)
    if not isPathInsideProject(venv_dir, project_dir):
        raise RuntimeError(f"recreate refused: {venv_dir} is outside project {project_dir}")
    rm = runner_rmtree or shutil.rmtree
    create = runner_create or createVenv
    pip = runner_pip or runPipInstall
    if os.path.exists(venv_dir):
        rm(venv_dir)
    python = create(base_python, venv_dir)
    cmd = buildPipInstallCommand(
        python,
        mode=MODE_SYNC,
        requirement_files=requirement_files,
        packages=packages,
        install_project=install_project,
        project_dir=project_dir,
    )
    # Only run pip if there is something to install beyond bare `pip install`
    if len(cmd) > 4:
        pip(cmd, cwd=project_dir)
    return python


def collectInstallSources(project) -> dict:
    """Collect available install sources for the wizard.

    Returns dict with keys:
      requirement_files: list[str]
      has_pyproject: bool
      unresolved_packages: list[str]
    """
    from .importutils import generateRequirementsFromProject

    project_dir = project.getProjectDir()
    req_files: list[str] = []
    if project_dir and os.path.isdir(project_dir):
        for path in sorted(Path(project_dir).glob("requirements*.txt")):
            if path.is_file():
                req_files.append(str(path.resolve()))
    has_pyproject = bool(project_dir and os.path.isfile(os.path.join(project_dir, "pyproject.toml")))
    packages: list[str] = []
    try:
        packages_set, _ = generateRequirementsFromProject(project.filesList)
        packages = sorted(packages_set)
    except Exception:
        _LOG.exception("collect unresolved packages failed")
    return {
        "requirement_files": req_files,
        "has_pyproject": has_pyproject,
        "unresolved_packages": packages,
    }


def saveInterpreterToProject(project, python_or_venv: str) -> None:
    """Persist interpreter into project props and clear session overlay."""
    path = os.path.abspath(python_or_venv)
    props = dict(project.props)
    props["pythoninterpreter"] = path
    project.updateProperties(props)
    clearSessionPythonInterpreter()


def bindInterpreter(project, python_path: str, *, persist: bool) -> None:
    """Save to project or set session overlay."""
    python_path = os.path.abspath(python_path)
    if persist:
        saveInterpreterToProject(project, python_path)
    else:
        setSessionPythonInterpreter(python_path)
