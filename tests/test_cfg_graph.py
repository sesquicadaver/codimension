# -*- coding: utf-8 -*-
"""R140.a: headless CFG graph model from control-flow parse."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

CASES = Path(__file__).resolve().parent / "conformance" / "cases"


def test_build_cfg_simple_function_and_if() -> None:
    from core.cfg import CfgEdgeKind, CfgNodeKind, build_cfg_graph

    source = "def f(x):\n    if x:\n        return 1\n    return 0\n"
    graph = build_cfg_graph(source)
    assert graph.entry_id and graph.exit_id
    assert graph.entry_id in graph.nodes and graph.exit_id in graph.nodes
    kinds = {n.kind for n in graph.nodes.values()}
    assert CfgNodeKind.FUNCTION in kinds
    assert CfgNodeKind.IF in kinds
    assert CfgNodeKind.RETURN in kinds
    assert any(e.kind == CfgEdgeKind.BODY for e in graph.edges)
    assert any(e.kind == CfgEdgeKind.TRUE for e in graph.edges)
    # ENTRY reaches a real node
    assert graph.successors(graph.entry_id)
    # At least one EXIT edge into global exit
    assert graph.predecessors(graph.exit_id)


def test_cfg_spans_are_half_open_slices() -> None:
    from core.cfg import CfgNodeKind, build_cfg_graph

    source = "x = 1\ny = 2\n"
    graph = build_cfg_graph(source)
    code_nodes = graph.nodes_of_kind(CfgNodeKind.CODE)
    assert code_nodes
    for node in code_nodes:
        assert 0 <= node.span.start <= node.span.end <= len(source)
        assert source[node.span.start : node.span.end]


def test_cfg_nested_scopes_fixture() -> None:
    from core.cfg import CfgNodeKind, build_cfg_graph

    source = (CASES / "nested_scopes.py").read_text(encoding="utf-8")
    graph = build_cfg_graph(source)
    assert graph.nodes_of_kind(CfgNodeKind.FUNCTION) or graph.nodes_of_kind(CfgNodeKind.CLASS)
    assert graph.errors == () or isinstance(graph.errors, tuple)


def test_cfg_match_case_fixture() -> None:
    from core.cfg import CfgEdgeKind, CfgNodeKind, build_cfg_graph

    path = CASES / "match_case.py"
    if not path.exists():
        pytest.skip("match_case fixture missing")
    source = path.read_text(encoding="utf-8")
    graph = build_cfg_graph(source)
    assert graph.nodes_of_kind(CfgNodeKind.MATCH)
    assert any(e.kind == CfgEdgeKind.CASE for e in graph.edges)


def test_cfg_loop_has_loop_back() -> None:
    from core.cfg import CfgEdgeKind, CfgNodeKind, build_cfg_graph

    graph = build_cfg_graph("for i in range(3):\n    x = i\n")
    assert graph.nodes_of_kind(CfgNodeKind.LOOP)
    assert any(e.kind == CfgEdgeKind.LOOP_BACK for e in graph.edges)


def test_from_control_flow_matches_build() -> None:
    from core.cfg import build_cfg_graph, from_control_flow
    from core.flow import parse_control_flow_from_memory

    source = "def g():\n    pass\n"
    a = build_cfg_graph(source)
    b = from_control_flow(parse_control_flow_from_memory(source))
    assert {n.kind for n in a.nodes.values()} == {n.kind for n in b.nodes.values()}
    assert len(a.edges) == len(b.edges)


def test_core_cfg_import_without_qt() -> None:
    root = Path(__file__).resolve().parents[1]
    code = (
        "import sys\n"
        f"sys.path.insert(0, {str(root / 'codimension')!r})\n"
        f"sys.path.insert(0, {str(root)!r})\n"
        "assert 'PyQt5' not in sys.modules\n"
        "from core.cfg import build_cfg_graph, CfgGraph\n"
        "g = build_cfg_graph('x=1\\n')\n"
        "assert isinstance(g, CfgGraph)\n"
        "assert 'PyQt5' not in sys.modules\n"
        "print('ok')\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)
    assert "ok" in proc.stdout
