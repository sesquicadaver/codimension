# -*- coding: utf-8 -*-
"""Project venv create/attach/update helpers (T140)."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from .venvutils import resolveVenvToPython

if TYPE_CHECKING:
    from .analysis_environment import AnalysisEnvironment

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

# Machine-readable interpreter probe (audit C02).
_PROBE_SCRIPT = (
    "import json,sys;"
    "print(json.dumps({"
    '"executable":sys.executable,'
    '"prefix":sys.prefix,'
    '"base_prefix":sys.base_prefix,'
    '"version_info":list(sys.version_info[:3]),'
    '"is_venv":sys.prefix!=sys.base_prefix'
    "}))"
)
_PROBE_TIMEOUT_SEC = 15


def probePythonInterpreter(python_path: str) -> dict:
    """Run ``python_path`` and return executable/prefix/version probe data (C02).

    Raises ``RuntimeError`` when the process fails or the payload is invalid.
    """
    if not python_path:
        raise RuntimeError("interpreter probe: empty path")
    path = os.path.abspath(python_path)
    if not os.path.isfile(path) or not os.access(path, os.X_OK):
        raise RuntimeError(f"interpreter probe: not an executable: {path}")
    try:
        completed = subprocess.run(
            [path, "-c", _PROBE_SCRIPT],
            check=False,
            capture_output=True,
            text=True,
            timeout=_PROBE_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"interpreter probe timed out: {path}") from exc
    except OSError as exc:
        raise RuntimeError(f"interpreter probe failed to start: {path}: {exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or f"exit {completed.returncode}").strip()
        raise RuntimeError(f"interpreter probe failed ({completed.returncode}): {detail}")
    try:
        payload = json.loads((completed.stdout or "").strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        raise RuntimeError(f"interpreter probe returned invalid JSON: {path}") from exc
    required = ("executable", "prefix", "base_prefix", "version_info", "is_venv")
    if not isinstance(payload, dict) or any(key not in payload for key in required):
        raise RuntimeError(f"interpreter probe missing fields: {path}")
    version = payload.get("version_info")
    if not (isinstance(version, list) and len(version) >= 2 and all(isinstance(x, int) for x in version[:3])):
        raise RuntimeError(f"interpreter probe bad version_info: {path}")
    payload["is_venv"] = bool(payload["is_venv"])
    return payload


def parsePyvenvCfg(venv_dir: str) -> dict[str, str]:
    """Parse ``pyvenv.cfg`` key/value pairs (empty dict if missing)."""
    cfg_path = os.path.join(os.path.abspath(venv_dir), "pyvenv.cfg")
    values: dict[str, str] = {}
    try:
        with open(cfg_path, encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                values[key.strip().lower()] = value.strip()
    except OSError:
        return {}
    return values


def resolveRecreateBasePython(venv_python: str) -> str:
    """Resolve the base interpreter for recreating ``venv_python``'s venv (C03).

    Prefers ``pyvenv.cfg`` ``executable`` / ``home``, then a version-matched
    ``pythonX.Y`` on ``PATH``. Uses IDE ``sys.executable`` only when its
    major.minor matches the current venv — never as a silent version upgrade.
    """
    path = os.path.abspath(venv_python)
    info = probePythonInterpreter(path)
    target = tuple(info["version_info"][:2])
    root = venvDirFromPython(path)
    if not root:
        raise RuntimeError(f"cannot resolve recreate base: no venv root for {path}")

    cfg = parsePyvenvCfg(root)
    candidates: list[str] = []
    exe = cfg.get("executable") or cfg.get("base-executable")
    if exe:
        candidates.append(exe)
    home = cfg.get("home")
    if home:
        if os.path.isfile(home) and os.access(home, os.X_OK):
            candidates.append(home)
        else:
            for name in (f"python{target[0]}.{target[1]}", "python3", "python"):
                candidates.append(os.path.join(home, name))

    which_name = f"python{target[0]}.{target[1]}"
    try:
        import shutil as _shutil

        found = _shutil.which(which_name)
        if found:
            candidates.append(found)
    except Exception:
        pass

    if sys.version_info[:2] == target:
        candidates.append(sys.executable)

    seen: set[str] = set()
    for candidate in candidates:
        cand = os.path.abspath(candidate)
        if cand in seen:
            continue
        seen.add(cand)
        if not os.path.isfile(cand) or not os.access(cand, os.X_OK):
            continue
        if isIdePythonEnvironment(cand) and os.path.realpath(cand) != os.path.realpath(sys.executable):
            # Skip non-sys IDE-tree noise; sys.executable is allowed when versions match.
            continue
        try:
            probed = probePythonInterpreter(cand)
        except RuntimeError:
            continue
        if tuple(probed["version_info"][:2]) != target:
            continue
        if probed.get("is_venv"):
            # Base must be a non-venv (or at least not the project venv itself).
            cand_root = venvDirFromPython(cand)
            if cand_root and os.path.realpath(cand_root) == os.path.realpath(root):
                continue
            # Prefer a true base interpreter when available.
            continue
        return cand

    # Second pass: allow a matching non-project venv as base (nested tools).
    for candidate in candidates:
        cand = os.path.abspath(candidate)
        if not os.path.isfile(cand) or not os.access(cand, os.X_OK):
            continue
        try:
            probed = probePythonInterpreter(cand)
        except RuntimeError:
            continue
        if tuple(probed["version_info"][:2]) != target:
            continue
        cand_root = venvDirFromPython(cand)
        if cand_root and os.path.realpath(cand_root) == os.path.realpath(root):
            continue
        return cand

    raise RuntimeError(
        f"cannot resolve base Python {target[0]}.{target[1]} to recreate {root}; "
        f"install python{target[0]}.{target[1]} or set pyvenv.cfg executable/home"
    )


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


def assertSafeMutableProjectPython(python_path: str, *, project_dir: str | None = None) -> str:
    """Return absolute python path after probe-based venv authenticity checks (C02).

    Requires a successful interpreter probe with ``is_venv``, matching
    ``pyvenv.cfg`` root / ``sys.prefix``, and (when ``project_dir`` is set) that
    the venv lies inside the project. Refuses the Codimension IDE environment.
    """
    if not python_path:
        raise RuntimeError("refusing pip/venv mutate: empty interpreter")
    path = os.path.abspath(python_path)
    if isIdePythonEnvironment(path):
        raise RuntimeError("refusing pip/venv mutate: target is the Codimension IDE interpreter/venv")
    if not os.path.isfile(path) or not os.access(path, os.X_OK):
        raise RuntimeError(f"refusing pip/venv mutate: not an executable: {path}")

    info = probePythonInterpreter(path)
    if not info.get("is_venv"):
        raise RuntimeError("refusing pip/venv mutate: target is not a virtual environment")

    root = venvDirFromPython(path)
    if not root:
        raise RuntimeError(f"refusing pip/venv mutate: missing pyvenv.cfg for {path}")
    resolved = resolveVenvToPython(root)
    if not resolved:
        raise RuntimeError(f"refusing pip/venv mutate: venv root has no python: {root}")
    if os.path.realpath(resolved) != os.path.realpath(path):
        raise RuntimeError(f"refusing pip/venv mutate: executable {path} does not match venv root {root}")
    if os.path.realpath(str(info["prefix"])) != os.path.realpath(root):
        raise RuntimeError(f"refusing pip/venv mutate: probe prefix {info['prefix']} != venv root {root}")
    if project_dir and not isPathInsideProject(root, project_dir):
        raise RuntimeError(f"refusing pip/venv mutate: venv outside project: {root}")
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
    project_dir = project.getProjectDir() if project is not None else None
    return assertSafeMutableProjectPython(path, project_dir=project_dir)


def getEffectiveProjectPython(project) -> str:
    """Resolve project Python for analysis: props → session → auto → IDE.

    When ``pythoninterpreter`` is set but invalid, falls back for *read-only*
    analysis only; status bar reports ``Env: broken`` via
    ``describeAnalysisPythonSource``. Mutating ops must use
    ``requireMutableProjectPython``.
    """
    env = buildAnalysisEnvironment(project)
    if env.source_kind == SOURCE_INVALID:
        return _resolveWithoutConfigured(project)[1]
    return env.python_path


def _project_uuid(project) -> str | None:
    """Return non-empty project UUID, or ``None``."""
    if project is None or not project.isLoaded():
        return None
    props = getattr(project, "props", None) or {}
    uid = str(props.get("uuid", "") or "").strip()
    return uid or None


def buildAnalysisEnvironment(project, *, for_tools: bool = False) -> AnalysisEnvironment:
    """Build an immutable ``AnalysisEnvironment`` for ``project`` (R111/R112).

    Single constructor path: ``describeAnalysisPythonSource`` → typed snapshot
    with site-packages roots and project id.

    When ``for_tools`` is True and the configured interpreter is broken, the
    snapshot uses the same read-only fallback as ``getEffectiveProjectPython``
    so lint/test drivers run against a usable interpreter.
    """
    from .analysis_environment import AnalysisEnvironment as _AnalysisEnvironment

    kind, path = describeAnalysisPythonSource(project)
    project_id = _project_uuid(project)
    if for_tools and kind == SOURCE_INVALID:
        kind, path = _resolveWithoutConfigured(project)
    return _AnalysisEnvironment.from_source(
        kind,
        path,
        project_id=project_id,
    )


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
    env = buildAnalysisEnvironment(project)
    label = _SOURCE_STATUS_LABELS.get(env.source_kind, "Env: IDE")
    if env.source_kind == SOURCE_INVALID:
        fallback = _resolveWithoutConfigured(project)[1]
        tip = f"configured missing: {env.python_path}\nanalysis fallback: {fallback}"
        return label, tip
    return label, env.python_path


def selectedUnresolvedPackages(enabled: bool, items: list[tuple[str, bool]]) -> list[str]:
    """Return packages selected for install when unresolved source is enabled.

    ``items`` is a list of ``(package_name, checked)``. When ``enabled`` is
    False, returns an empty list (opt-in; T141).
    """
    if not enabled:
        return []
    return [name for name, checked in items if name and checked]


def requestAnalysisEnvironmentRefresh(project) -> None:
    """Invalidate import caches and force project analysis rescan (T141/R113)."""
    import importlib

    importlib.invalidate_caches()
    try:
        from .analysis_cache import invalidate_analysis_caches

        # Env change can leave brief/flow entries stale even when mtimes match.
        invalidate_analysis_caches("env")
    except Exception:
        _LOG.debug("analysis cache env invalidate skipped", exc_info=True)
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


def makeStagingVenvDir(venv_dir: str) -> str:
    """Return a unique sibling staging path next to ``venv_dir`` (audit D02/B07).

    Staging names use a ``.cdm-venv-stage-`` prefix so root auto-detect
    (``.venv`` / ``venv`` / ``env``) never picks them up.
    """
    import time

    abs_dir = os.path.abspath(venv_dir)
    parent = os.path.dirname(abs_dir) or "."
    base = os.path.basename(abs_dir) or "venv"
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in base)[:64] or "venv"
    return os.path.join(parent, f".cdm-venv-stage-{safe}-{os.getpid()}-{time.time_ns()}")


def discardStagedVenv(staged_dir: str | None) -> None:
    """Best-effort removal of a staging (or backup) directory."""
    if not staged_dir:
        return
    try:
        if os.path.lexists(staged_dir):
            shutil.rmtree(staged_dir, ignore_errors=True)
    except OSError:
        _LOG.debug("discard staged venv failed: %s", staged_dir, exc_info=True)


def commitStagedVenv(venv_dir: str, staged_dir: str) -> None:
    """Atomically replace ``venv_dir`` with ``staged_dir`` (same-parent rename).

    Existing ``venv_dir`` is moved aside first and removed only after the new
    directory is in place. On swap failure the previous tree is restored when
    possible (audit D02/B07).
    """
    import time

    venv_dir = os.path.abspath(venv_dir)
    staged_dir = os.path.abspath(staged_dir)
    if venv_dir == staged_dir:
        raise RuntimeError("staging path must differ from final venv destination")
    if not os.path.isdir(staged_dir):
        raise RuntimeError(f"staged venv missing: {staged_dir}")

    backup = None
    if os.path.lexists(venv_dir):
        backup = f"{venv_dir}.cdm-bak-{os.getpid()}-{time.time_ns()}"
        try:
            os.rename(venv_dir, backup)
        except OSError as exc:
            raise RuntimeError(f"cannot move existing venv aside: {venv_dir}: {exc}") from exc
    try:
        os.rename(staged_dir, venv_dir)
    except OSError as exc:
        if backup and not os.path.lexists(venv_dir):
            try:
                os.rename(backup, venv_dir)
                backup = None
            except OSError:
                _LOG.exception("failed to restore venv backup after commit error")
        raise RuntimeError(f"cannot commit staged venv to {venv_dir}: {exc}") from exc
    discardStagedVenv(backup)


def createVenvInPlace(base_python: str, venv_dir: str) -> str:
    """Create a venv at ``venv_dir`` without staging (caller owns transaction).

    ``venv_dir`` must not already be a usable venv. Returns the new python path.
    """
    base_python = base_python or sys.executable
    venv_dir = os.path.abspath(venv_dir)
    if resolveVenvToPython(venv_dir):
        raise RuntimeError(f"venv already exists at {venv_dir}")
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


def createVenv(base_python: str, venv_dir: str, project_dir: str | None = None) -> str:
    """Create a venv transactionally; return path to the new python executable.

    Builds under a sibling staging directory and renames into place so a failed
    ``python -m venv`` never leaves a half-written destination (audit D02/B07).
    Raises ``RuntimeError`` on failure or unsafe destination.
    """
    base_python = base_python or sys.executable
    venv_dir = validateVenvDestination(venv_dir, project_dir, for_recreate=False)
    staged = makeStagingVenvDir(venv_dir)
    try:
        createVenvInPlace(base_python, staged)
        commitStagedVenv(venv_dir, staged)
    except Exception:
        discardStagedVenv(staged)
        raise
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


def runPipInstall(cmd: list[str], *, cwd: str | None = None, project_dir: str | None = None) -> None:
    """Execute pip install command; raise RuntimeError on failure.

    Refuses when the target interpreter is the Codimension IDE environment.
    """
    if cmd:
        assertSafeMutableProjectPython(cmd[0], project_dir=project_dir)
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
    expected_version: tuple[int, int] | None = None,
    runner_probe=None,
) -> str:
    """Recreate a venv with staging so the old tree survives until commit.

    Flow (audit D02/B07 + C02): create+probe(+pip) into a sibling staging
    directory, then rename over the final path. The previous venv is removed
    only after the new tree is committed. ``runner_create(base, staged_path)``
    must create *in place* at the given staging path (no nested commit to the
    final dir).

    ``expected_version`` (major, minor), when set, must match the staged
    interpreter probe (audit C03).

    ``runner_rmtree`` is retained for tests/legacy callers; the happy path no
    longer deletes the live venv before create.

    Refuses unsafe destinations via :func:`validateVenvDestination` (audit P0).
    Returns new python path.
    """
    venv_dir = validateVenvDestination(venv_dir, project_dir, for_recreate=True)
    create = runner_create or (lambda base, path: createVenvInPlace(base, path))
    pip = runner_pip or runPipInstall
    probe = runner_probe or probePythonInterpreter
    # Legacy hook: some tests inject rmtree; transactional path does not need it.
    _ = runner_rmtree or shutil.rmtree
    staged = makeStagingVenvDir(venv_dir)
    try:
        python = create(base_python, staged)
        info = probe(python)
        if not info.get("is_venv"):
            raise RuntimeError(f"staged interpreter is not a venv: {python}")
        if expected_version is not None and tuple(info["version_info"][:2]) != tuple(expected_version):
            raise RuntimeError(
                f"recreate base produced Python {info['version_info'][0]}.{info['version_info'][1]}, "
                f"expected {expected_version[0]}.{expected_version[1]}"
            )
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
            try:
                pip(cmd, cwd=project_dir, project_dir=project_dir)
            except TypeError:
                pip(cmd, cwd=project_dir)
        commitStagedVenv(venv_dir, staged)
    except Exception:
        discardStagedVenv(staged)
        raise
    final_python = resolveVenvToPython(venv_dir)
    if not final_python:
        raise RuntimeError(f"venv recreated but python not found under {venv_dir}")
    probe(final_python)
    return final_python


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
