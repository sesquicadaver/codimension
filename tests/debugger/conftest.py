# -*- coding: utf-8 -*-
"""Fixtures for debugger session integration (T100).

Other suites (e.g. ``test_importutils``) stub ``ui.qt`` / ``utils.run`` at
collection time. This package restores real modules before each test.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CODIM = ROOT / "codimension"


def _ensure_imp_shim() -> None:
    """Install full ``imp`` compat for yapsy (load_module + PKG_DIRECTORY)."""
    try:
        from imp_compat import ensure_imp_compat
    except ImportError:
        from codimension.imp_compat import ensure_imp_compat  # type: ignore[no-redef]

    ensure_imp_compat()


def _module_under_codimension(mod: object) -> bool:
    """True if module/package resolves under the repo ``codimension/`` tree."""
    path = getattr(mod, "__file__", None)
    if path:
        return "/codimension/" in os.path.abspath(path).replace("\\", "/")
    pkg_path = getattr(mod, "__path__", None)
    if pkg_path is None:
        return False
    try:
        first = os.path.abspath(list(pkg_path)[0]).replace("\\", "/")
    except Exception:
        return False
    return "/codimension/" in first


def _restore_real_modules() -> None:
    """Drop collection-time stubs that break session e2e imports."""
    prefixes = ("ui.", "utils.", "debugger.", "parsers.")
    roots = ("ui", "utils", "debugger", "parsers", "cdmpyparser", "cdmcfparser")
    dirty = False
    for name in list(sys.modules):
        if name not in roots and not name.startswith(prefixes):
            continue
        mod = sys.modules[name]
        if name == "cdmpyparser" and not hasattr(mod, "getBriefModuleInfoFromFile"):
            del sys.modules[name]
            dirty = True
            continue
        if name == "cdmcfparser" and not hasattr(mod, "getControlFlowFromMemory"):
            del sys.modules[name]
            dirty = True
            continue
        if not _module_under_codimension(mod):
            del sys.modules[name]
            dirty = True
            continue
        # Real file path but incomplete stub (e.g. utils.fileutils without loadJSON).
        if name == "utils.fileutils" and not hasattr(mod, "loadJSON"):
            del sys.modules[name]
            dirty = True
        if name == "ui.qt" and not hasattr(getattr(mod, "QApplication", None), "instance"):
            del sys.modules[name]
            dirty = True
        if name == "utils.run" and not hasattr(mod, "_debuggerClientPath"):
            del sys.modules[name]
            dirty = True
    if dirty:
        importlib.invalidate_caches()
        if "parsers" in sys.modules:
            importlib.reload(sys.modules["parsers"])
        else:
            import parsers  # noqa: F401


@pytest.fixture(scope="session", autouse=True)
def _debugger_session_env():
    """Offscreen Qt + path/imp shims for the whole debugger suite."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _ensure_imp_shim()
    for path in (str(ROOT), str(CODIM)):
        if path not in sys.path:
            sys.path.insert(0, path)
    _restore_real_modules()
    import parsers  # noqa: F401


@pytest.fixture(autouse=True)
def _isolate_from_collection_stubs():
    """Reclaim real ui/utils/debugger modules before every debugger test."""
    _restore_real_modules()
    yield


@pytest.fixture
def qapp(_debugger_session_env, _isolate_from_collection_stubs):
    """Per-test QApplication (shared process-wide instance)."""
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def reset_globals(qapp):
    """Drop GlobalData singleton around each debugger test."""
    from utils.globals import resetGlobalDataForTests

    resetGlobalDataForTests()
    yield qapp
    resetGlobalDataForTests()


@pytest.fixture
def force_stop_at_first_line(reset_globals):
    """Ensure debugger settings stop at the first executable line."""
    from utils.settings import DebuggerSettings, Settings

    settings = Settings()
    dbg = DebuggerSettings()
    dbg.stopAtFirstLine = True
    dbg.reportExceptions = True
    dbg.traceInterpreter = False
    settings.setDebuggerSettings(dbg)
    return settings


@pytest.fixture
def skin_ready(reset_globals):
    """Bootstrap Skin for icon/font paths (T120 widget tests only — not autouse)."""
    from utils.globals import GlobalData
    from utils.settings import Settings
    from utils.skin import Skin, populateSampleSkin

    Settings()
    populateSampleSkin()
    skin = Skin()
    skin.loadByName(Settings()["skin"])
    GlobalData().skin = skin
    return GlobalData()


@pytest.fixture
def widget_debugger(skin_ready, qapp):
    """CodimensionDebugger on MixinDebuggerHost without RunManager (T120 R2)."""
    del qapp
    from debugger.server import CodimensionDebugger

    from .host import create_mixin_host

    host = create_mixin_host()
    debugger = CodimensionDebugger(host)
    host._debugger = debugger
    return host, debugger
