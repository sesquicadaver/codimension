# -*- coding: utf-8 -*-
"""R135: OverlayLayer protocol, registry, and flow/editor attach hosts."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
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


@dataclass
class RecordingOverlay:
    """Records OverlayContext values for attach-point tests."""

    layer_id: str = "recording"
    events: list = field(default_factory=list)

    def on_update(self, context) -> None:
        self.events.append(context)


def test_empty_overlay_register_and_notify() -> None:
    from core.overlay import EmptyOverlayLayer, OverlayContext, OverlayLayer, OverlayRegistry

    layer = EmptyOverlayLayer()
    assert isinstance(layer, OverlayLayer)
    registry = OverlayRegistry()
    registry.register(layer)
    assert registry.has("empty")
    registry.notify(OverlayContext(reason="redraw", path="a.py", surface="flow"))


def test_flow_and_editor_hosts_invoke_hook() -> None:
    from utils.overlay_host import (
        editor_overlay_host,
        ensure_empty_overlay,
        flow_overlay_host,
        notify_editor_overlays,
        notify_flow_overlays,
    )

    flow = flow_overlay_host()
    editor = editor_overlay_host()
    # Isolate from other tests that may have registered layers.
    flow.registry = type(flow.registry)()
    editor.registry = type(editor.registry)()

    ensure_empty_overlay(flow)
    ensure_empty_overlay(editor)
    rec_flow = RecordingOverlay(layer_id="rec_flow")
    rec_editor = RecordingOverlay(layer_id="rec_editor")
    flow.register(rec_flow)
    editor.register(rec_editor)

    notify_flow_overlays("redraw", path="/tmp/f.py")
    notify_editor_overlays("update", path="/tmp/e.py")

    assert len(rec_flow.events) == 1
    assert rec_flow.events[0].reason == "redraw"
    assert rec_flow.events[0].surface == "flow"
    assert rec_flow.events[0].path == "/tmp/f.py"

    assert len(rec_editor.events) == 1
    assert rec_editor.events[0].reason == "update"
    assert rec_editor.events[0].surface == "editor"


def test_flowuiwidget_calls_notify_flow_overlays() -> None:
    """Static attach-point check: redrawScene notifies flow overlays."""
    path = Path(__file__).resolve().parents[1] / "codimension" / "editor" / "flowuiwidget.py"
    text = path.read_text(encoding="utf-8")
    assert "notify_flow_overlays" in text
    assert 'notify_flow_overlays("redraw"' in text or "notify_flow_overlays('redraw'" in text


def test_texteditor_calls_notify_editor_overlays() -> None:
    """Static attach-point check: setAnalysisMessages notifies editor overlays."""
    path = Path(__file__).resolve().parents[1] / "codimension" / "editor" / "texteditor.py"
    text = path.read_text(encoding="utf-8")
    assert "notify_editor_overlays" in text
    assert 'notify_editor_overlays("update"' in text or "notify_editor_overlays('update'" in text


def test_core_overlay_import_without_qt() -> None:
    root = Path(__file__).resolve().parents[1]
    code = (
        "import sys\n"
        f"sys.path.insert(0, {str(root / 'codimension')!r})\n"
        f"sys.path.insert(0, {str(root)!r})\n"
        "assert 'PyQt5' not in sys.modules\n"
        "from core.overlay import OverlayLayer, OverlayRegistry, EmptyOverlayLayer\n"
        "assert 'PyQt5' not in sys.modules\n"
        "print('ok')\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)
    assert "ok" in proc.stdout
