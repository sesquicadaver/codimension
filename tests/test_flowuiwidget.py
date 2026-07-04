# -*- coding: utf-8 -*-
"""Tests for flow UI smart zoom constants (no full editor import chain)."""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FLOWUIWIDGET_PATH = os.path.join(ROOT, "codimension", "editor", "flowuiwidget.py")
_SETTINGS_PATH = os.path.join(ROOT, "codimension", "utils", "settings.py")


def _read_settings_class_constant(name):
    """Read SettingsWrapper class constant without importing settings."""
    pattern = re.compile(rf"^\s+{re.escape(name)}\s*=\s*(-?\d+)", re.MULTILINE)
    with open(_SETTINGS_PATH, encoding="utf-8") as handle:
        match = pattern.search(handle.read())
    assert match is not None, f"{name} not found in SettingsWrapper"
    return int(match.group(1))


def test_settings_max_smart_zoom_allows_fs_view():
    """Settings clamp range must include the FS dependencies zoom level."""
    assert _read_settings_class_constant("MAX_SMART_ZOOM") == 4
    assert _read_settings_class_constant("MIN_SMART_ZOOM") == -3


def test_flowuiwidget_max_zoom_includes_fs():
    """FS zoom must not be capped below SMART_ZOOM_FS in flowuiwidget."""
    with open(_FLOWUIWIDGET_PATH, encoding="utf-8") as handle:
        source = handle.read()
    assert "SMART_ZOOM_FS = 4" in source
    assert "SMART_ZOOM_MAX = SMART_ZOOM_FS" in source
    assert "SMART_ZOOM_MAX = SMART_ZOOM_CLASS_FUNC" not in source
    assert "# TODO: Till FS zoom is implemented" not in source
