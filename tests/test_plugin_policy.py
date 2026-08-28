# -*- coding: utf-8 -*-
"""R191 / A210: plugin policy before import (manifest-first; disabled never import)."""

from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _purge_incomplete_stubs(*prefixes: str) -> None:
    for name in list(sys.modules):
        if not any(name == p or name.startswith(p + ".") for p in prefixes):
            continue
        mod = sys.modules.get(name)
        if mod is None:
            continue
        file_name = (getattr(mod, "__file__", None) or "").replace("\\", "/")
        if "codimension/" not in file_name and "codimension\\" not in file_name:
            del sys.modules[name]


def _ensure_imp() -> None:
    try:
        from imp_compat import ensure_imp_compat
    except ImportError:
        from codimension.imp_compat import ensure_imp_compat  # type: ignore[no-redef]

    ensure_imp_compat()


@pytest.fixture
def plugin_manager_mod(monkeypatch, tmp_path):
    """Import pluginmanager with SETTINGS_DIR under tmp and empty search paths."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PyQt5.QtWidgets")
    _purge_incomplete_stubs("utils", "ui", "plugins", "yapsy")
    codim = str(ROOT / "codimension")
    if codim not in sys.path:
        sys.path.insert(0, codim)
    _ensure_imp()

    import plugins.manager.pluginmanager as pm

    settings_dir = tmp_path / "settings"
    settings_dir.mkdir()
    monkeypatch.setattr(pm, "SETTINGS_DIR", str(settings_dir) + os.sep)

    disabled: list[str] = []
    settings = MagicMock()
    settings.__getitem__ = lambda self, key: disabled if key == "disabledPlugins" else None
    settings.__setitem__ = lambda self, key, value: disabled.clear() or disabled.extend(value)

    monkeypatch.setattr(pm, "Settings", MagicMock(return_value=settings))
    return pm, settings_dir, disabled


def _write_plugin_package(root: Path, name: str, marker_module: str) -> Path:
    """Create a minimal WizardInterface-shaped plugin package + .cdmp."""
    pkg = root / name
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        textwrap.dedent(
            f"""\
            # marker import side effect for R191 tests
            import {marker_module} as _marker_mod

            from plugins.categories.wizardiface import WizardInterface


            class DemoPlugin(WizardInterface):
                def activate(self, settings, globalData):
                    WizardInterface.activate(self, settings, globalData)

                def deactivate(self):
                    WizardInterface.deactivate(self)

                def isIDEVersionCompatible(self, ideVersion):
                    return True
            """
        ),
        encoding="utf-8",
    )
    (pkg / f"{name}.cdmp").write_text(
        textwrap.dedent(
            f"""\
            [Core]
            Name = {name}
            Module = .

            [Documentation]
            Author = Test
            Version = 1.0.0
            Description = R191 test plugin
            """
        ),
        encoding="utf-8",
    )
    return pkg


def test_normalize_and_guess_category(plugin_manager_mod, tmp_path):
    pm, _, _ = plugin_manager_mod
    assert pm.normalize_plugin_path(str(tmp_path / "x" / ".")) == str((tmp_path / "x").resolve())
    src = tmp_path / "plug"
    src.mkdir()
    init = src / "__init__.py"
    init.write_text("class X(VersionControlSystemInterface):\n    pass\n", encoding="utf-8")
    assert pm.guess_plugin_category_from_source(str(src / "__init__")) == "VersionControlSystemInterface"


def test_r191_disabled_plugin_never_imported(plugin_manager_mod, tmp_path, monkeypatch):
    """Disabled path must stay manifest-only: plugin package code must not run."""
    pm, _settings_dir, disabled = plugin_manager_mod

    marker_name = "cdm_r191_import_marker_disabled"
    marker_path = tmp_path / f"{marker_name}.py"
    marker_path.write_text("IMPORTED = True\n", encoding="utf-8")
    sys.path.insert(0, str(tmp_path))

    plugins_root = tmp_path / "plugins"
    plugins_root.mkdir()
    pkg = _write_plugin_package(plugins_root, "evilplug", marker_name)
    disabled.append(f"{pm.CDMPluginManager.USER_DISABLED}:::{pm.normalize_plugin_path(pkg)}:::user")

    mgr = pm.CDMPluginManager.__new__(pm.CDMPluginManager)
    from ui.qt import QObject
    from yapsy.PluginManager import PluginManager

    QObject.__init__(mgr)
    PluginManager.__init__(mgr, None, [str(plugins_root)], "cdmp")
    mgr.inactivePlugins = {}
    mgr.activePlugins = {}
    mgr.unknownPlugins = []
    mgr._pendingImportByPath = {}
    mgr._policySkippedCandidates = []

    mgr.collectPlugins()
    assert marker_name not in sys.modules

    assert len(mgr._policySkippedCandidates) == 1
    assert pm.normalize_plugin_path(pkg) in mgr._pendingImportByPath

    mgr._CDMPluginManager__registerPolicySkippedPlugins()
    inactive = [p for plugs in mgr.inactivePlugins.values() for p in plugs]
    assert len(inactive) == 1
    assert inactive[0].getName() == "evilplug"
    assert inactive[0].getObject() is None
    # Still never imported after stub registration.
    assert marker_name not in sys.modules


def test_r191_enabled_plugin_still_imports(plugin_manager_mod, tmp_path):
    """Non-disabled candidates are still imported by collectPlugins."""
    pm, _, disabled = plugin_manager_mod
    assert disabled == []

    marker_name = "cdm_r191_import_marker_ok"
    # Real tiny module so ``import marker`` succeeds.
    marker_path = tmp_path / f"{marker_name}.py"
    marker_path.write_text("IMPORTED = True\n", encoding="utf-8")
    sys.path.insert(0, str(tmp_path))

    plugins_root = tmp_path / "plugins"
    plugins_root.mkdir()
    _write_plugin_package(plugins_root, "goodplug", marker_name)

    mgr = pm.CDMPluginManager.__new__(pm.CDMPluginManager)
    from ui.qt import QObject
    from yapsy.PluginManager import PluginManager

    QObject.__init__(mgr)
    PluginManager.__init__(mgr, None, [str(plugins_root)], "cdmp")
    mgr.inactivePlugins = {}
    mgr.activePlugins = {}
    mgr.unknownPlugins = []
    mgr._pendingImportByPath = {}
    mgr._policySkippedCandidates = []

    mgr.collectPlugins()
    assert marker_name in sys.modules
    assert getattr(sys.modules[marker_name], "IMPORTED", False) is True
    assert mgr._policySkippedCandidates == []
