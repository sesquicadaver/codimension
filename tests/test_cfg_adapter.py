# -*- coding: utf-8 -*-
"""R140.b: flowui consumes core.cfg via thin adapter."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

CASES = Path(__file__).resolve().parent / "conformance" / "cases"


def test_bind_cfg_graph_attaches_model() -> None:
    from core.cfg import CfgNodeKind, from_control_flow
    from core.flow import parse_control_flow_from_memory
    from flowui.cfg_adapter import bind_cfg_graph, get_bound_cfg, module_entry_successor, require_bound_cfg

    source = "def f(x):\n    if x:\n        return 1\n    return 0\n"
    cf = parse_control_flow_from_memory(source)
    canvas = SimpleNamespace()
    graph = bind_cfg_graph(canvas, cf)
    assert get_bound_cfg(canvas) is graph
    assert require_bound_cfg(canvas) is graph
    assert graph.entry_id and graph.exit_id
    assert graph.nodes_of_kind(CfgNodeKind.FUNCTION)
    assert module_entry_successor(graph)
    # Same structural model as headless build from the same CF object
    assert len(graph.nodes) == len(from_control_flow(cf).nodes)


def test_nodes_for_line_covers_function() -> None:
    from core.flow import parse_control_flow_from_memory
    from flowui.cfg_adapter import bind_cfg_graph, nodes_for_line

    source = "def f():\n    x = 1\n"
    cf = parse_control_flow_from_memory(source)
    canvas = SimpleNamespace()
    graph = bind_cfg_graph(canvas, cf)
    hits = nodes_for_line(graph, 1)
    assert hits
    assert any(n.label == "f" or n.kind.value == "function" for n in hits)


def test_require_bound_cfg_raises_without_bind() -> None:
    from flowui.cfg_adapter import require_bound_cfg

    with pytest.raises(RuntimeError, match="cfg_graph"):
        require_bound_cfg(SimpleNamespace())


def test_layout_module_binds_cfg_graph() -> None:
    """VirtualCanvas.layoutModule must attach cfg_graph (behavior parity)."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PyQt5.QtWidgets")
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    root = str(Path(__file__).resolve().parents[1] / "codimension")
    if root not in sys.path:
        sys.path.insert(0, root)

    # Drop incomplete collection stubs (same pattern as Flow UI coupling tests).
    for name in list(sys.modules):
        if name == "ui" or name.startswith("ui.") or name == "utils" or name.startswith("utils."):
            mod = sys.modules.get(name)
            path = getattr(mod, "__file__", None) or ""
            if not path or "/codimension/" not in path.replace("\\", "/"):
                del sys.modules[name]
            elif name == "ui.qt" and not hasattr(mod, "QBrush"):
                del sys.modules[name]
            elif name == "utils" and not hasattr(mod, "limits") and not getattr(mod, "__path__", None):
                del sys.modules[name]

    import importlib

    importlib.invalidate_caches()
    import parsers  # noqa: F401
    import ui.qt as qt

    assert hasattr(qt, "QBrush"), "ui.qt stub still active"

    from cdmcfparser import getControlFlowFromMemory
    from flowui.vcanvas import VirtualCanvas

    class _Settings:
        noComment = True
        hidecomments = True
        hidedocstrings = True
        hideexcepts = False
        hidedecors = False
        itemID = 0

        def __getattr__(self, name: str):
            if name.endswith("Metrics"):
                return None
            return 4

    source = (CASES / "nested_scopes.py").read_text(encoding="utf-8")
    cf = getControlFlowFromMemory(source)
    assert not cf.errors, cf.errors
    canvas = VirtualCanvas(_Settings(), None, None, [], {}, None)
    canvas.layoutModule(cf)
    assert canvas.cfg_graph is not None
    assert canvas.cfg_graph.entry_id
    assert canvas.cfg_graph.nodes
    assert app is not None
