# -*- coding: utf-8 -*-
#
# codimension - native crash telemetry (R273)
# Copyright (C) 2026  Codimension Team
# The license is described in the LICENSE file at the root directory.
#

"""Enable ``faulthandler`` and keep a crash-context snapshot (R273).

On native abort (SIGSEGV/SIGABRT, …) CPython dumps all threads into
``SETTINGS_DIR/native_crashes.log``. A sibling ``crash_context.txt`` holds
process/version/lifecycle breadcrumbs that survive when Python cannot run
cleanup code.

Qt/PyQt version strings are injected by the UI entrypoint (utils must not
import Qt — R103/R195).
"""

from __future__ import annotations

import os
import sys
import threading
import time
from collections import deque
from typing import Any, TextIO

_NATIVE_CRASH_LOG = "native_crashes.log"
_CRASH_CONTEXT = "crash_context.txt"
_MAX_EVENTS = 64

_fault_file: TextIO | None = None
_enabled_path: str | None = None
_settings_dir: str | None = None
_version: str = ""
_commit_sha: str = ""
_last_command: str = ""
_pyqt_version: str = "unknown"
_qt_version: str = "unknown"
_events: deque[str] = deque(maxlen=_MAX_EVENTS)
_lock = threading.RLock()


def native_crash_log_name() -> str:
    """Basename of the faulthandler dump file under SETTINGS_DIR."""
    return _NATIVE_CRASH_LOG


def crash_context_name() -> str:
    """Basename of the lifecycle/context snapshot under SETTINGS_DIR."""
    return _CRASH_CONTEXT


def note_lifecycle(event: str, *, detail: str = "") -> None:
    """Append a timestamped lifecycle breadcrumb (ring buffer)."""
    text = (event or "").strip()
    if not text:
        return
    extra = (detail or "").strip()
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {text}"
    if extra:
        line = f"{line} | {extra}"
    with _lock:
        _events.append(line)


def note_active_command(command: str) -> None:
    """Remember the last user/IDE command label for crash dumps."""
    global _last_command
    with _lock:
        _last_command = (command or "").strip()


def set_qt_versions(*, pyqt: str = "", qt: str = "") -> None:
    """Record PyQt/Qt version strings supplied by the UI layer."""
    global _pyqt_version, _qt_version
    with _lock:
        if pyqt:
            _pyqt_version = str(pyqt)
        if qt:
            _qt_version = str(qt)


def _resolve_commit_sha() -> str:
    explicit = (os.environ.get("CDM_COMMIT_SHA") or os.environ.get("GITHUB_SHA") or "").strip()
    if explicit:
        return explicit[:40]
    try:
        import cdmverspec

        sha = getattr(cdmverspec, "commit_sha", "") or ""
        if isinstance(sha, str) and sha.strip():
            return sha.strip()[:40]
    except Exception:
        pass
    return "unknown"


def _python_threads() -> list[str]:
    lines: list[str] = []
    for thr in threading.enumerate():
        lines.append(f"{thr.name} ident={thr.ident} daemon={thr.daemon} alive={thr.is_alive()}")
    return lines


def _background_registry_state() -> dict[str, Any]:
    try:
        from .background_task_registry import get_background_task_registry

        return get_background_task_registry().dump_state()
    except Exception:
        return {"error": "registry unavailable"}


def _project_path() -> str:
    try:
        from .globals import GlobalData

        project = GlobalData().project
        if project is not None and getattr(project, "isLoaded", lambda: False)():
            return str(getattr(project, "fileName", "") or "")
    except Exception:
        pass
    return ""


def collect_crash_context(
    *,
    version: str | None = None,
    commit_sha: str | None = None,
) -> str:
    """Build a plain-text crash context snapshot (R273)."""
    with _lock:
        events = list(_events)
        command = _last_command
        ver = version if version is not None else _version
        sha = commit_sha if commit_sha is not None else (_commit_sha or _resolve_commit_sha())
        pyqt = _pyqt_version
        qt = _qt_version
    registry = _background_registry_state()
    lines = [
        "codimension crash context (R273)",
        f"timestamp={time.strftime('%Y-%m-%dT%H:%M:%S')}",
        f"pid={os.getpid()}",
        f"version={ver or 'unknown'}",
        f"commit_sha={sha}",
        f"python={sys.version.split()[0]}",
        f"pyqt={pyqt}",
        f"qt={qt}",
        f"project_path={_project_path() or '(none)'}",
        f"last_active_command={command or '(none)'}",
        f"background_registry={registry!r}",
        "active_qthreads: via background_registry.active (R271 probes)",
        "python_threads:",
    ]
    for thr in _python_threads():
        lines.append(f"  - {thr}")
    lines.append("lifecycle_events:")
    if events:
        for ev in events:
            lines.append(f"  - {ev}")
    else:
        lines.append("  - (none)")
    lines.append("")
    return "\n".join(lines)


def write_crash_context(settings_dir: str | None = None) -> str | None:
    """Rewrite ``crash_context.txt`` under settings_dir; return path or None."""
    base = settings_dir or _settings_dir
    if not base:
        return None
    path = os.path.join(base, _CRASH_CONTEXT)
    try:
        os.makedirs(base, exist_ok=True)
        payload = collect_crash_context()
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(payload)
        return path
    except OSError:
        return None


def enable_crash_telemetry(
    settings_dir: str,
    *,
    version: str = "",
    commit_sha: str = "",
    pyqt_version: str = "",
    qt_version: str = "",
) -> str:
    """Enable faulthandler dumping into SETTINGS_DIR and seed context (R273).

    Returns the absolute path of ``native_crashes.log``. Idempotent: a second
    call with the same directory is a no-op that still refreshes context.
    """
    global _fault_file, _enabled_path, _settings_dir, _version, _commit_sha

    base = os.path.abspath(settings_dir)
    os.makedirs(base, exist_ok=True)
    log_path = os.path.join(base, _NATIVE_CRASH_LOG)

    if pyqt_version or qt_version:
        set_qt_versions(pyqt=pyqt_version, qt=qt_version)

    with _lock:
        _settings_dir = base
        _version = version or _version
        _commit_sha = (commit_sha or _resolve_commit_sha()).strip() or "unknown"

    if _enabled_path == log_path and _fault_file is not None:
        note_lifecycle("crash_telemetry_refresh")
        write_crash_context(_settings_dir)
        return log_path

    import faulthandler

    handle = open(log_path, "a", encoding="utf-8")  # noqa: SIM115 — kept for process life
    handle.write(
        f"\n------ faulthandler enabled at {time.strftime('%Y-%m-%dT%H:%M:%S')} "
        f"pid={os.getpid()} version={_version} sha={_commit_sha} ------\n"
    )
    handle.flush()
    faulthandler.enable(file=handle, all_threads=True)
    _fault_file = handle
    _enabled_path = log_path
    note_lifecycle("crash_telemetry_enabled", detail=log_path)
    write_crash_context(_settings_dir)
    return log_path


def reset_for_tests() -> None:
    """Disable faulthandler file and clear breadcrumbs (unit tests only)."""
    global _fault_file, _enabled_path, _settings_dir, _version, _commit_sha, _last_command
    global _pyqt_version, _qt_version
    import faulthandler

    try:
        faulthandler.disable()
    except Exception:
        pass
    if _fault_file is not None:
        try:
            _fault_file.close()
        except Exception:
            pass
    with _lock:
        _fault_file = None
        _enabled_path = None
        _settings_dir = None
        _version = ""
        _commit_sha = ""
        _last_command = ""
        _pyqt_version = "unknown"
        _qt_version = "unknown"
        _events.clear()
