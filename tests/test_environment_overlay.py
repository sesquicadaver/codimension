# -*- coding: utf-8 -*-
"""R160: environment overlay badges via OverlayLayer."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import parsers  # noqa: E402,F401
import pytest

_CODIM = Path(__file__).resolve().parents[1] / "codimension"


@pytest.fixture(autouse=True)
def _purge_stubs():
    import importlib

    def _under(mod: object) -> bool:
        path = getattr(mod, "__file__", None)
        if path:
            return "/codimension/" in os.path.abspath(path).replace("\\", "/")
        return False

    dirty = False
    for name in list(sys.modules):
        if name not in ("ui", "utils") and not name.startswith(("ui.", "utils.")):
            continue
        if _under(sys.modules[name]):
            continue
        del sys.modules[name]
        dirty = True
    if dirty:
        importlib.invalidate_caches()
        if str(_CODIM) not in sys.path:
            sys.path.insert(0, str(_CODIM))
    yield


def test_format_env_badge_info_source_and_path() -> None:
    from utils.environment_overlay import format_env_badge_info

    info = format_env_badge_info("session", "/home/me/proj/.venv/bin/python")
    assert info.source_badge == "env:session"
    assert info.source_kind == "session"
    assert "python" in info.path_badge
    assert info.tooltip.endswith("python")


def test_truncate_path_badge_keeps_basename() -> None:
    from utils.environment_overlay import truncate_path_badge

    long_path = "/very/long/directory/structure/that/exceeds/limit/.venv/bin/python"
    badge = truncate_path_badge(long_path, max_chars=28)
    assert badge.endswith("python")
    assert len(badge) <= 28
    assert "…" in badge


def test_environment_layer_register_notify_and_sink() -> None:
    from utils.environment_overlay import ENVIRONMENT_LAYER_ID, EnvironmentOverlayLayer
    from utils.overlay_host import flow_overlay_host, notify_flow_overlays

    host = flow_overlay_host()
    host.registry = type(host.registry)()
    layer = EnvironmentOverlayLayer()
    host.register(layer)
    assert host.registry.has(ENVIRONMENT_LAYER_ID)

    seen: list = []
    layer.add_sink(seen.append)
    notify_flow_overlays("env")
    assert layer.last_badge is not None
    assert layer.last_badge.source_badge.startswith("env:")
    assert len(seen) == 1
    assert seen[0] is layer.last_badge


def test_ensure_environment_overlay_idempotent() -> None:
    from utils.environment_overlay import ENVIRONMENT_LAYER_ID, ensure_environment_overlay
    from utils.overlay_host import flow_overlay_host

    host = flow_overlay_host()
    host.registry = type(host.registry)()
    a = ensure_environment_overlay(host)
    b = ensure_environment_overlay(host)
    assert a is b
    assert host.registry.has(ENVIRONMENT_LAYER_ID)


def test_env_badge_qlabel_widget_smoke() -> None:
    """Widget smoke: source + path badges render on QLabel pair (acceptance)."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PyQt5.QtWidgets")
    from PyQt5.QtWidgets import QApplication, QHBoxLayout, QLabel, QWidget

    _app = QApplication.instance() or QApplication([])
    from utils.environment_overlay import format_env_badge_info

    info = format_env_badge_info("configured", "/opt/proj/.venv/bin/python", tooltip="/opt/proj/.venv/bin/python")
    host = QWidget()
    layout = QHBoxLayout(host)
    source = QLabel()
    path = QLabel()
    layout.addWidget(source)
    layout.addWidget(path)
    source.setText(info.source_badge)
    path.setText(info.path_badge)
    source.setToolTip(info.tooltip)
    path.setToolTip(info.tooltip)
    assert source.text() == "env:project"
    assert "python" in path.text()
    assert source.toolTip() == info.tooltip
    assert _app is not None


def test_flowuinavbar_has_env_badge_api_static() -> None:
    path = Path(__file__).resolve().parents[1] / "codimension" / "editor" / "flowuinavbar.py"
    text = path.read_text(encoding="utf-8")
    assert "setEnvBadges" in text
    assert "__envSourceBadge" in text
    assert "__envPathBadge" in text


def test_flowuiwidget_registers_environment_overlay_static() -> None:
    path = Path(__file__).resolve().parents[1] / "codimension" / "editor" / "flowuiwidget.py"
    text = path.read_text(encoding="utf-8")
    assert "ensure_environment_overlay" in text
    assert "__onEnvOverlayBadge" in text


def test_mainstatusbar_notifies_env_overlay_static() -> None:
    path = Path(__file__).resolve().parents[1] / "codimension" / "ui" / "mainstatusbar.py"
    text = path.read_text(encoding="utf-8")
    assert 'notify_flow_overlays("env")' in text or "notify_flow_overlays('env')" in text
