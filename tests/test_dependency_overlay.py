# -*- coding: utf-8 -*-
"""R161: DependencyGraph edge-heat overlay via OverlayLayer."""

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


def test_compute_edge_heats_normalizes() -> None:
    from utils.dependency_graph import build_dependency_graph_from_sources
    from utils.dependency_overlay import compute_edge_heats, heat_to_rgb, max_outgoing_heat

    root = "/tmp/r161proj"
    graph = build_dependency_graph_from_sources(
        [
            (f"{root}/a.py", "from b import x, y, z\nimport os\n"),
            (f"{root}/b.py", "def x():\n    return 1\n"),
        ],
        root=root,
    )
    heats = compute_edge_heats(graph)
    assert heats
    assert max(h.normalized for h in heats) == 1.0
    assert all(0.0 < h.normalized <= 1.0 for h in heats)
    edge_ab = next(h for h in heats if h.source.endswith("a") and h.target.endswith("b"))
    assert edge_ab.raw >= 1
    assert max_outgoing_heat(heats, edge_ab.source) >= edge_ab.normalized
    r, g, b = heat_to_rgb(1.0)
    assert r > g and r > b


def test_summarize_deps_heat_badges() -> None:
    from utils.dependency_graph import build_dependency_graph_from_sources
    from utils.dependency_overlay import summarize_deps_heat

    root = "/tmp/r161sum"
    graph = build_dependency_graph_from_sources(
        [
            (f"{root}/pkg/a.py", "from pkg import b\nfrom pkg.b import helper\n"),
            (f"{root}/pkg/b.py", "def helper():\n    return 1\n"),
        ],
        root=root,
    )
    summary = summarize_deps_heat(graph, focus_module="pkg.a")
    assert summary.edges_badge.startswith("deps:")
    assert summary.edge_count >= 1
    assert "hot:" in summary.hot_badge
    assert "pkg.a" in summary.hot_badge or "→" in summary.hot_badge
    assert summary.focus_max_heat >= 0.0
    assert "Hottest edges" in summary.tooltip


def test_dependency_layer_register_notify_and_sink(tmp_path: Path) -> None:
    from utils.dependency_overlay import DEPENDENCY_LAYER_ID, DependencyOverlayLayer
    from utils.overlay_host import flow_overlay_host, notify_flow_overlays

    mod = tmp_path / "m.py"
    mod.write_text("import sys\n", encoding="utf-8")

    host = flow_overlay_host()
    host.registry = type(host.registry)()
    layer = DependencyOverlayLayer()
    host.register(layer)
    assert host.registry.has(DEPENDENCY_LAYER_ID)

    seen: list = []
    layer.add_sink(seen.append)
    notify_flow_overlays("deps", path=str(mod))
    assert layer.last_badge is not None
    assert layer.last_badge.edges_badge.startswith("deps:")
    assert len(seen) == 1


def test_ensure_dependency_overlay_idempotent() -> None:
    from utils.dependency_overlay import DEPENDENCY_LAYER_ID, ensure_dependency_overlay
    from utils.overlay_host import flow_overlay_host

    host = flow_overlay_host()
    host.registry = type(host.registry)()
    a = ensure_dependency_overlay(host)
    b = ensure_dependency_overlay(host)
    assert a is b
    assert host.registry.has(DEPENDENCY_LAYER_ID)


def test_deps_heat_qlabel_widget_smoke() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PyQt5.QtWidgets")
    from PyQt5.QtWidgets import QApplication, QHBoxLayout, QLabel, QWidget

    _app = QApplication.instance() or QApplication([])
    from utils.dependency_graph import build_dependency_graph_from_sources
    from utils.dependency_overlay import summarize_deps_heat

    graph = build_dependency_graph_from_sources(
        [("/tmp/w.py", "import sys\n")],
        root="/tmp",
    )
    info = summarize_deps_heat(graph)
    host = QWidget()
    layout = QHBoxLayout(host)
    edges = QLabel()
    hot = QLabel()
    layout.addWidget(edges)
    layout.addWidget(hot)
    edges.setText(info.edges_badge)
    hot.setText(info.hot_badge)
    assert edges.text().startswith("deps:")
    assert _app is not None


def test_flowuiwidget_registers_dependency_overlay_static() -> None:
    path = Path(__file__).resolve().parents[1] / "codimension" / "editor" / "flowuiwidget.py"
    text = path.read_text(encoding="utf-8")
    assert "ensure_dependency_overlay" in text
    assert "__onDepsOverlayBadge" in text
    assert 'notify_flow_overlays("deps"' in text or "notify_flow_overlays('deps'" in text


def test_depsitems_applies_connector_heat_static() -> None:
    path = Path(__file__).resolve().parents[1] / "codimension" / "diagram" / "depsitems.py"
    text = path.read_text(encoding="utf-8")
    assert "heat_to_rgb" in text
    assert "deps_focus_max_heat" in text


def test_flowuinavbar_has_deps_badge_api_static() -> None:
    path = Path(__file__).resolve().parents[1] / "codimension" / "editor" / "flowuinavbar.py"
    text = path.read_text(encoding="utf-8")
    assert "setDepsHeatBadges" in text
    assert "__depsEdgesBadge" in text
