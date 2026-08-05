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

# Analysis Python source kinds (T141) — used by status bar / tooling.
SOURCE_CONFIGURED = "configured"
SOURCE_SESSION = "session"
SOURCE_AUTO = "auto"
SOURCE_IDE = "ide"
SOURCE_INVALID = "invalid"  # configured path set but not resolvable (audit P0)

_SOURCE_STATUS_LABELS = {
    SOURCE_CONFIGURED: "Env: project",
    SOURCE_SESSION: "Env: session",
    SOURCE_AUTO: "Env: auto",
    SOURCE_IDE: "Env: IDE",
    SOURCE_INVALID: "Env: broken",
}

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


def _configuredDisplayPath(project, interp: str) -> str:
    """Absolute display path for a configured interpreter (may be missing)."""
    if not os.path.isabs(interp):
        project_dir = project.getProjectDir() if project is not None else None
        if project_dir:
            return os.path.normpath(os.path.join(project_dir, interp))
    return os.path.abspath(interp) if interp else interp


def _tryResolveConfigured(project, interp: str) -> str | None:
    """Resolve configured interpreter to an executable, or ``None`` if invalid.

    Never falls back to ``sys.executable`` (audit P0 — no silent IDE swap).
    """
    if not interp:
        return None
    candidate = _configuredDisplayPath(project, interp)
    if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
        return os.path.abspath(candidate)
    venv_python = resolveVenvToPython(candidate)
    if venv_python:
        return venv_python
    return None


def _resolveWithoutConfigured(project) -> tuple[str, str]:
    """Resolve session → auto → IDE (ignores ``pythoninterpreter`` prop)."""
    session = getSessionPythonInterpreter()
    if session:
        if os.path.isfile(session) and os.access(session, os.X_OK):
            return SOURCE_SESSION, os.path.abspath(session)
        venv_python = resolveVenvToPython(session)
        if venv_python:
            return SOURCE_SESSION, venv_python

    project_dir = project.getProjectDir() if project is not None else None
    if project_dir:
        for venv_name in ROOT_VENV_NAMES:
            venv_path = os.path.join(project_dir, venv_name)
            venv_python = resolveVenvToPython(venv_path)
            if venv_python:
                return SOURCE_AUTO, venv_python
    return SOURCE_IDE, sys.executable


def isIdePythonEnvironment(python_path: str) -> bool:
    """True if ``python_path`` belongs to the running Codimension IDE environment.

    Identity is by **venv root** (``pyvenv.cfg`` parent vs ``sys.prefix``), not by
    ``realpath(python)``. On POSIX, distinct venvs often symlink ``bin/python`` to
    the same base interpreter; comparing executable realpaths falsely rejects
    project venvs (audit P0 @ f5196a67).
    """
    if not python_path:
        return True
    try:
        path = os.path.abspath(python_path)
        ide_root = os.path.realpath(sys.prefix)
        candidate_root = venvDirFromPython(path)
        if candidate_root is not None:
            return os.path.realpath(candidate_root) == ide_root

        # Bare / non-venv interpreter: only the IDE's own executable (or a file
        # physically under sys.prefix) is treated as IDE.
        if os.path.realpath(path) == os.path.realpath(sys.executable):
            return True
        path_real = os.path.realpath(path)
        if ide_root and (path_real == ide_root or path_real.startswith(ide_root + os.sep)):
            return True
    except Exception:
        return True
    return False


def assertSafeMutableProjectPython(python_path: str) -> str:
    """Return absolute python path or raise if mutating it would touch the IDE."""
    if not python_path:
        raise RuntimeError("refusing pip/venv mutate: empty interpreter")
    path = os.path.abspath(python_path)
    if isIdePythonEnvironment(path):
        raise RuntimeError("refusing pip/venv mutate: target is the Codimension IDE interpreter/venv")
    if not os.path.isfile(path) or not os.access(path, os.X_OK):
        raise RuntimeError(f"refusing pip/venv mutate: not an executable: {path}")
    return path


def requireMutableProjectPython(project) -> str:
    """Python allowed for pip install / recreate (raises on broken or IDE target)."""
    kind, path = describeAnalysisPythonSource(project)
    if kind == SOURCE_INVALID:
        raise RuntimeError(
            "configured pythoninterpreter is missing or not executable; "
            "fix Project Properties / VENV… before Update VENV"
        )
    if kind == SOURCE_IDE:
        raise RuntimeError(
            "no project venv configured; use VENV… to create/attach one (refusing to mutate the IDE Python)"
        )
    return assertSafeMutableProjectPython(path)


def getEffectiveProjectPython(project) -> str:
    """Resolve project Python for analysis: props → session → auto → IDE.

    When ``pythoninterpreter`` is set but invalid, falls back for *read-only*
    analysis only; status bar reports ``Env: broken`` via
    ``describeAnalysisPythonSource``. Mutating ops must use
    ``requireMutableProjectPython``.
    """
    kind, path = describeAnalysisPythonSource(project)
    if kind == SOURCE_INVALID:
        return _resolveWithoutConfigured(project)[1]
    return path


def describeAnalysisPythonSource(project) -> tuple[str, str]:
    """Return ``(kind, path)`` for import/analysis / status bar.

    Kinds: ``configured``, ``session``, ``auto``, ``ide``, ``invalid``
    (configured path set but not resolvable — path is the configured display
    path, not a silent IDE fallback).
    """
    if project is None or not project.isLoaded():
        return SOURCE_IDE, sys.executable

    interp = project.props.get("pythoninterpreter", "").strip()
    if interp:
        resolved = _tryResolveConfigured(project, interp)
        if resolved:
            return SOURCE_CONFIGURED, resolved
        return SOURCE_INVALID, _configuredDisplayPath(project, interp)

    return _resolveWithoutConfigured(project)


def formatAnalysisEnvStatus(project) -> tuple[str, str]:
    """Return ``(status_bar_text, tooltip_path)`` for the analysis environment."""
    kind, path = describeAnalysisPythonSource(project)
    label = _SOURCE_STATUS_LABELS.get(kind, "Env: IDE")
    if kind == SOURCE_INVALID:
        fallback = _resolveWithoutConfigured(project)[1]
        tip = f"configured missing: {path}\nanalysis fallback: {fallback}"
        return label, tip
    return label, path


def selectedUnresolvedPackages(enabled: bool, items: list[tuple[str, bool]]) -> list[str]:
    """Return packages selected for install when unresolved source is enabled.

    ``items`` is a list of ``(package_name, checked)``. When ``enabled`` is
    False, returns an empty list (opt-in; T141).
    """
    if not enabled:
        return []
    return [name for name, checked in items if name and checked]


def requestAnalysisEnvironmentRefresh(project) -> None:
    """Invalidate import caches and force project analysis rescan (T141)."""
    import importlib

    importlib.invalidate_caches()
    try:
        from .run import getVenvSitePackages

        if project is not None and project.isLoaded():
            site = getVenvSitePackages(getEffectiveProjectPython(project))
            if site:
                site_real = os.path.realpath(site)
                for key in list(sys.path_importer_cache):
                    if isinstance(key, str) and os.path.realpath(key).startswith(site_real):
                        del sys.path_importer_cache[key]
    except Exception:
        _LOG.debug("site-packages importer cache cleanup skipped", exc_info=True)

    if project is not None and project.isLoaded():
        refresh = getattr(project, "refreshAnalysisEnvironment", None)
        if callable(refresh):
            refresh()


def isPythonInterpreterConfigured(project) -> bool:
    """True when ``pythoninterpreter`` project prop is non-empty."""
    if project is None or not project.isLoaded():
        return False
    return bool(project.props.get("pythoninterpreter", "").strip())


def venvSetupActionEnabled(project) -> bool:
    """VENV… menu: create/attach when unset, or reattach when configured path is broken."""
    if project is None or not project.isLoaded():
        return False
    if not isPythonInterpreterConfigured(project):
        return True
    kind, _ = describeAnalysisPythonSource(project)
    return kind == SOURCE_INVALID


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
    """Best-effort venv root from ``.../bin/python`` or ``.../Scripts/python.exe``.

    Requires ``pyvenv.cfg`` so system ``/usr/bin/python`` is not treated as a venv.
    Uses the path as given (not ``realpath``) so symlink-based venvs keep their
    own root even when the executable resolves to a shared base interpreter.
    """
    if not python_path:
        return None
    bin_dir = os.path.dirname(os.path.abspath(python_path))
    if os.path.basename(bin_dir) not in ("bin", "Scripts"):
        return None
    root = os.path.dirname(bin_dir)
    if os.path.isfile(os.path.join(root, "pyvenv.cfg")):
        return root
    return None


def isPathInsideProject(venv_path: str, project_dir: str) -> bool:
    """True if ``venv_path`` is under ``project_dir`` (realpath prefix)."""
    try:
        venv_real = os.path.realpath(venv_path)
        proj_real = os.path.realpath(project_dir)
        return venv_real == proj_real or venv_real.startswith(proj_real + os.sep)
    except Exception:
        return False


def validateVenvDestination(
    venv_dir: str,
    project_dir: str | None = None,
    *,
    for_recreate: bool = False,
) -> str:
    """Fail-closed destination checks for create/recreate (audit P0 @ 9df7eca7).

    Returns absolute ``venv_dir``. Raises ``RuntimeError`` when unsafe:

    - empty path
    - outside ``project_dir`` or equal to project root
    - destination is a symlink
    - destination is the active Codimension IDE env (``sys.prefix``)
    - create onto an existing valid venv (must attach / recreate instead)
    - create onto a non-empty non-venv directory
    """
    if not venv_dir or not str(venv_dir).strip():
        raise RuntimeError("venv destination is empty")
    venv_dir = os.path.abspath(str(venv_dir).strip())

    if project_dir:
        proj_abs = os.path.abspath(project_dir)
        if os.path.normpath(venv_dir) == os.path.normpath(proj_abs):
            raise RuntimeError("venv destination must not be the project root")
        if not isPathInsideProject(venv_dir, project_dir):
            raise RuntimeError(f"venv destination outside project: {venv_dir}")

    if os.path.islink(venv_dir):
        raise RuntimeError(f"venv destination is a symlink (refusing): {venv_dir}")

    ide_root = os.path.realpath(sys.prefix)
    dest_real = os.path.realpath(venv_dir) if os.path.lexists(venv_dir) else venv_dir
    if dest_real == ide_root:
        raise RuntimeError("venv destination is the active Codimension IDE environment")

    if os.path.exists(venv_dir):
        if not os.path.isdir(venv_dir):
            raise RuntimeError(f"venv destination exists and is not a directory: {venv_dir}")
        if resolveVenvToPython(venv_dir):
            if for_recreate:
                return venv_dir
            raise RuntimeError(
                f"venv already exists at {venv_dir}; select it to attach, or use Update VENV… → Recreate"
            )
        try:
            if any(os.scandir(venv_dir)):
                raise RuntimeError(f"venv destination is not empty: {venv_dir}")
        except RuntimeError:
            raise
        except OSError as exc:
            raise RuntimeError(f"cannot inspect venv destination: {venv_dir}: {exc}") from exc

    return venv_dir


def createVenv(base_python: str, venv_dir: str, project_dir: str | None = None) -> str:
    """Create a venv; return path to the new python executable.

    Raises ``RuntimeError`` on failure or unsafe destination.
    """
    base_python = base_python or sys.executable
    venv_dir = validateVenvDestination(venv_dir, project_dir, for_recreate=False)
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
    """Execute pip install command; raise RuntimeError on failure.

    Refuses when the target interpreter is the Codimension IDE environment.
    """
    if cmd:
        assertSafeMutableProjectPython(cmd[0])
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

    Refuses unsafe destinations via :func:`validateVenvDestination` (audit P0).
    Returns new python path.
    """
    venv_dir = validateVenvDestination(venv_dir, project_dir, for_recreate=True)
    rm = runner_rmtree or shutil.rmtree
    create = runner_create or (lambda base, path: createVenv(base, path, project_dir=project_dir))
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
