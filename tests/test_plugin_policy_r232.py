# -*- coding: utf-8 -*-
"""R232 — plugin re-enable must re-check manifest + file identity before import."""

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
    """Import pluginmanager with SETTINGS_DIR under tmp."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PyQt5.QtWidgets")
    _purge_incomplete_stubs("utils", "ui", "plugins", "yapsy", "cdmplugins")
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
    """Create a WizardInterface plugin package + complete [Codimension] .cdmp."""
    pkg = root / name
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        textwrap.dedent(
            f"""\
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
            Description = R232 test plugin

            [Codimension]
            Category = WizardInterface
            MinIDEVersion = 4.0.0
            MinPluginAPI = 1
            RequiredCapabilities = wizard
            Entrypoint = .
            """
        ),
        encoding="utf-8",
    )
    return pkg


def _new_manager(pm, plugins_root: Path):
    mgr = pm.CDMPluginManager.__new__(pm.CDMPluginManager)
    from ui.qt import QObject
    from yapsy.PluginManager import PluginManager

    QObject.__init__(mgr)
    PluginManager.__init__(mgr, None, [str(plugins_root)], "cdmp")
    mgr.inactivePlugins = {}
    mgr.activePlugins = {}
    mgr.unknownPlugins = []
    mgr._pendingImportByPath = {}
    mgr._pendingIdentityByPath = {}
    mgr._policySkippedCandidates = []
    mgr._preImportRejects = {}
    return mgr


def test_r232_identity_capture_changes_on_source_edit(tmp_path: Path) -> None:
    from plugins.policy import capture_plugin_file_identity

    src = tmp_path / "__init__.py"
    src.write_text("a = 1\n", encoding="utf-8")
    info = tmp_path / "p.cdmp"
    info.write_text("[Core]\nName = x\nModule = .\n", encoding="utf-8")
    first = capture_plugin_file_identity(info_path=str(info), module_filepath=str(tmp_path / "__init__"))
    src.write_text("a = 2\n", encoding="utf-8")
    second = capture_plugin_file_identity(info_path=str(info), module_filepath=str(tmp_path / "__init__"))
    assert first != second
    assert first.info_sha256 == second.info_sha256
    assert first.source_sha256 != second.source_sha256


def test_r232_validate_rejects_mutated_identity(tmp_path: Path) -> None:
    from plugins.policy import capture_plugin_file_identity, validate_candidate_before_import

    src = tmp_path / "__init__.py"
    src.write_text(
        "from plugins.categories.wizardiface import WizardInterface\nclass X(WizardInterface):\n    pass\n",
        encoding="utf-8",
    )
    info = tmp_path / "p.cdmp"
    info.write_text(
        textwrap.dedent(
            """\
            [Core]
            Name = Mut
            Module = .

            [Codimension]
            Category = WizardInterface
            MinIDEVersion = 4.0.0
            MinPluginAPI = 1
            RequiredCapabilities = wizard
            Entrypoint = .
            """
        ),
        encoding="utf-8",
    )
    expected = capture_plugin_file_identity(info_path=str(info), module_filepath=str(tmp_path / "__init__"))
    src.write_text("print('evil side effect')\n" + src.read_text(encoding="utf-8"), encoding="utf-8")
    decision = validate_candidate_before_import(
        info_path=str(info),
        module_filepath=str(tmp_path / "__init__"),
        name="Mut",
        version="1.0.0",
        plugin_path=str(tmp_path),
        expected_identity=expected,
        ide_version="5.0.0",
        require_manifest=True,
    )
    assert not decision.ok
    assert "changed since collection" in decision.reason


def test_r232_materialize_denies_after_manifest_strip(plugin_manager_mod, tmp_path, monkeypatch):
    """Enable path must not import if .cdmp Codimension block was removed after deferral."""
    pm, _settings_dir, disabled = plugin_manager_mod
    monkeypatch.setattr(pm.CDMPluginManager, "_CDMPluginManager__hostIdeVersion", staticmethod(lambda: "5.0.0"))

    marker_name = "cdm_r232_import_marker_denied"
    (tmp_path / f"{marker_name}.py").write_text("IMPORTED = True\n", encoding="utf-8")
    sys.path.insert(0, str(tmp_path))

    plugins_root = tmp_path / "plugins"
    plugins_root.mkdir()
    pkg = _write_plugin_package(plugins_root, "deferredplug", marker_name)
    disabled.append(f"{pm.CDMPluginManager.USER_DISABLED}:::{pm.normalize_plugin_path(pkg)}:::user")

    mgr = _new_manager(pm, plugins_root)
    mgr.collectPlugins()
    assert marker_name not in sys.modules
    norm = pm.normalize_plugin_path(pkg)
    assert norm in mgr._pendingImportByPath
    assert norm in mgr._pendingIdentityByPath

    # Mutate identity: strip Codimension (policy would also fail) and change bytes.
    cdmp = pkg / "deferredplug.cdmp"
    cdmp.write_text(
        textwrap.dedent(
            """\
            [Core]
            Name = deferredplug
            Module = .

            [Documentation]
            Author = Test
            Version = 1.0.0
            Description = stripped Codimension
            """
        ),
        encoding="utf-8",
    )

    mgr._CDMPluginManager__registerPolicySkippedPlugins()
    inactive = [p for plugs in mgr.inactivePlugins.values() for p in plugs]
    assert len(inactive) == 1
    stub = inactive[0]

    with pytest.raises(RuntimeError, match="pre-import gate"):
        mgr.materializePlugin(stub)
    assert marker_name not in sys.modules
    assert stub.getObject() is None
    assert norm not in mgr._pendingImportByPath


def test_r232_materialize_ok_when_files_unchanged(plugin_manager_mod, tmp_path, monkeypatch):
    """Clean enable path still imports when identity + policy hold."""
    pm, _settings_dir, disabled = plugin_manager_mod
    monkeypatch.setattr(pm.CDMPluginManager, "_CDMPluginManager__hostIdeVersion", staticmethod(lambda: "5.0.0"))

    marker_name = "cdm_r232_import_marker_ok"
    (tmp_path / f"{marker_name}.py").write_text("IMPORTED = True\n", encoding="utf-8")
    sys.path.insert(0, str(tmp_path))

    plugins_root = tmp_path / "plugins"
    plugins_root.mkdir()
    pkg = _write_plugin_package(plugins_root, "okdeferred", marker_name)
    disabled.append(f"{pm.CDMPluginManager.USER_DISABLED}:::{pm.normalize_plugin_path(pkg)}:::user")

    mgr = _new_manager(pm, plugins_root)
    mgr.collectPlugins()
    assert marker_name not in sys.modules

    mgr._CDMPluginManager__registerPolicySkippedPlugins()
    inactive = [p for plugs in mgr.inactivePlugins.values() for p in plugs]
    stub = inactive[0]
    mgr.materializePlugin(stub)
    assert marker_name in sys.modules
    assert stub.getObject() is not None
