# -*- coding: utf-8 -*-
"""R193 / A221: Settings non-dict JSON + lazy singleton."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

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


@pytest.fixture
def settings_mod(monkeypatch, tmp_path):
    """Import settings with SETTINGS_DIR under tmp; lazy singleton reset."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PyQt5.QtWidgets")
    _purge_incomplete_stubs("utils", "ui")
    codim = str(ROOT / "codimension")
    if codim not in sys.path:
        sys.path.insert(0, codim)

    import utils.settings as settings

    settings.resetSettingsSingletonForTests()
    settings_dir = tmp_path / "settings"
    settings_dir.mkdir()
    monkeypatch.setattr(settings, "SETTINGS_DIR", str(settings_dir) + os.sep)
    yield settings, settings_dir
    settings.resetSettingsSingletonForTests()


def test_r193_import_does_not_create_singleton(monkeypatch, tmp_path):
    """Importing utils.settings must not instantiate SettingsWrapper."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PyQt5.QtWidgets")
    _purge_incomplete_stubs("utils", "ui")
    # Drop cached module so import path runs again.
    for name in list(sys.modules):
        if name == "utils.settings" or name.startswith("utils.settings."):
            del sys.modules[name]
    codim = str(ROOT / "codimension")
    if codim not in sys.path:
        sys.path.insert(0, codim)

    import utils.settings as settings

    settings.resetSettingsSingletonForTests()
    assert settings._SETTINGS_SINGLETON is None  # noqa: SLF001
    # Module attribute SETTINGS_SINGLETON is lazy via __getattr__.
    assert "SETTINGS_SINGLETON" not in settings.__dict__


def test_r193_non_dict_json_uses_defaults(settings_mod):
    settings, settings_dir = settings_mod
    path = settings_dir / "settings.json"
    path.write_text("[]\n", encoding="utf-8")

    wrapper = settings.SettingsWrapper()
    assert wrapper["zoom"] == 0
    disk = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(disk, dict)
    assert "zoom" in disk


def test_r193_non_dict_string_json_uses_defaults(settings_mod):
    settings, settings_dir = settings_mod
    path = settings_dir / "settings.json"
    path.write_text('"oops"\n', encoding="utf-8")

    wrapper = settings.SettingsWrapper()
    assert wrapper["skin"] == "default"
    assert isinstance(json.loads(path.read_text(encoding="utf-8")), dict)


def test_r193_lazy_settings_callable(settings_mod):
    settings, settings_dir = settings_mod
    assert settings._SETTINGS_SINGLETON is None  # noqa: SLF001
    first = settings.Settings()
    second = settings.Settings()
    assert first is second
    assert settings._SETTINGS_SINGLETON is first  # noqa: SLF001
    assert (settings_dir / "settings.json").is_file()
