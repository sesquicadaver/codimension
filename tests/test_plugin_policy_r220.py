# -*- coding: utf-8 -*-
"""R220 — fail-closed plugin policy before import."""

from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from plugins.capabilities import negotiate_plugin_capabilities
from plugins.policy import (
    build_static_plugin_policy,
    evaluate_static_plugin_policy,
    extract_capability_spec_from_source,
    extract_min_ide_version_from_source,
)

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


def _write_plugin(
    root: Path,
    name: str,
    *,
    marker_module: str,
    body: str,
    cdmp_extra: str = "",
) -> Path:
    pkg = root / name
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(body, encoding="utf-8")
    (pkg / f"{name}.cdmp").write_text(
        textwrap.dedent(
            f"""\
            [Core]
            Name = {name}
            Module = .

            [Documentation]
            Author = Test
            Version = 1.0.0
            Description = R220 test plugin
            {cdmp_extra}
            """
        ),
        encoding="utf-8",
    )
    return pkg


def _make_manager(pm, plugins_root: Path):
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
    mgr._preImportRejects = {}
    return mgr


def test_extract_capability_and_min_ide_from_source() -> None:
    text = textwrap.dedent(
        """\
        from packaging.version import Version
        from plugins.capabilities import PluginCapabilitySpec

        def isIDEVersionCompatible(ideVersion):
            return Version(ideVersion) >= Version("4.7.1")

        def getCapabilityRequirements():
            return PluginCapabilitySpec(
                min_api_version=1,
                required=frozenset({"wizard", "vcs"}),
            )
        """
    )
    assert extract_min_ide_version_from_source(text) == "4.7.1"
    spec = extract_capability_spec_from_source(text)
    assert spec is not None
    assert spec.required == frozenset({"wizard", "vcs"})
    assert negotiate_plugin_capabilities(spec).ok


def test_manifest_codimension_section(tmp_path: Path) -> None:
    info = tmp_path / "p.cdmp"
    info.write_text(
        textwrap.dedent(
            """\
            [Core]
            Name = X
            Module = .

            [Codimension]
            Category = WizardInterface
            MinIDEVersion = 9.9.9
            MinPluginAPI = 1
            RequiredCapabilities = telepathy
            """
        ),
        encoding="utf-8",
    )
    src = tmp_path / "__init__.py"
    src.write_text("class X:\n    pass\n", encoding="utf-8")
    policy = build_static_plugin_policy(info_path=str(info), module_filepath=str(tmp_path / "__init__"))
    assert policy.category == "WizardInterface"
    assert policy.min_ide_version == "9.9.9"
    decision = evaluate_static_plugin_policy(policy, ide_version="5.0.0")
    assert not decision.ok
    assert decision.conflict_code == 2  # incompatible IDE first


def test_r220_missing_capability_never_imported(plugin_manager_mod, tmp_path, monkeypatch):
    pm, _, _ = plugin_manager_mod
    monkeypatch.setattr(pm.CDMPluginManager, "_CDMPluginManager__hostIdeVersion", staticmethod(lambda: "5.0.0"))

    marker_name = "cdm_r220_cap_marker"
    (tmp_path / f"{marker_name}.py").write_text("IMPORTED = True\n", encoding="utf-8")
    sys.path.insert(0, str(tmp_path))

    plugins_root = tmp_path / "plugins"
    plugins_root.mkdir()
    body = textwrap.dedent(
        f"""\
        import {marker_name} as _marker_mod
        from plugins.capabilities import PluginCapabilitySpec
        from plugins.categories.wizardiface import WizardInterface

        class DemoPlugin(WizardInterface):
            def activate(self, settings, globalData):
                WizardInterface.activate(self, settings, globalData)

            def deactivate(self):
                WizardInterface.deactivate(self)

            def isIDEVersionCompatible(self, ideVersion):
                return True

            @staticmethod
            def getCapabilityRequirements():
                return PluginCapabilitySpec(required=frozenset({{"telepathy"}}))
        """
    )
    _write_plugin(plugins_root, "capfail", marker_module=marker_name, body=body)
    mgr = _make_manager(pm, plugins_root)
    mgr.collectPlugins()
    assert marker_name not in sys.modules
    assert any(pm.normalize_plugin_path(c[2].path) in mgr._preImportRejects for c in mgr._policySkippedCandidates)


def test_r220_unknown_category_never_imported(plugin_manager_mod, tmp_path, monkeypatch):
    pm, _, _ = plugin_manager_mod
    monkeypatch.setattr(pm.CDMPluginManager, "_CDMPluginManager__hostIdeVersion", staticmethod(lambda: "5.0.0"))

    marker_name = "cdm_r220_cat_marker"
    (tmp_path / f"{marker_name}.py").write_text("IMPORTED = True\n", encoding="utf-8")
    sys.path.insert(0, str(tmp_path))

    plugins_root = tmp_path / "plugins"
    plugins_root.mkdir()
    body = textwrap.dedent(
        f"""\
        import {marker_name} as _marker_mod

        class DemoPlugin:
            pass
        """
    )
    _write_plugin(plugins_root, "nocat", marker_module=marker_name, body=body)
    mgr = _make_manager(pm, plugins_root)
    mgr.collectPlugins()
    assert marker_name not in sys.modules
    rejects = list(mgr._preImportRejects.values())
    assert rejects
    assert rejects[0][0] == pm.CDMPluginManager.BAD_BASE_CLASS


def test_r220_compatible_plugin_still_imports(plugin_manager_mod, tmp_path, monkeypatch):
    pm, _, _ = plugin_manager_mod
    monkeypatch.setattr(pm.CDMPluginManager, "_CDMPluginManager__hostIdeVersion", staticmethod(lambda: "5.0.0"))

    marker_name = "cdm_r220_ok_marker"
    (tmp_path / f"{marker_name}.py").write_text("IMPORTED = True\n", encoding="utf-8")
    sys.path.insert(0, str(tmp_path))

    plugins_root = tmp_path / "plugins"
    plugins_root.mkdir()
    body = textwrap.dedent(
        f"""\
        import {marker_name} as _marker_mod
        from packaging.version import Version
        from plugins.capabilities import PluginCapabilitySpec
        from plugins.categories.wizardiface import WizardInterface

        class DemoPlugin(WizardInterface):
            def activate(self, settings, globalData):
                WizardInterface.activate(self, settings, globalData)

            def deactivate(self):
                WizardInterface.deactivate(self)

            def isIDEVersionCompatible(self, ideVersion):
                return Version(ideVersion) >= Version("4.0.0")

            @staticmethod
            def getCapabilityRequirements():
                return PluginCapabilitySpec(
                    min_api_version=1,
                    required=frozenset({{"wizard"}}),
                )
        """
    )
    _write_plugin(plugins_root, "okplug", marker_module=marker_name, body=body)
    mgr = _make_manager(pm, plugins_root)
    mgr.collectPlugins()
    assert marker_name in sys.modules
    assert mgr._preImportRejects == {}
