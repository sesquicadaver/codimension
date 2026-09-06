# -*- coding: utf-8 -*-
"""R216: CFG loop-else and non-exhaustive match paths (audit P1-11)."""

from __future__ import annotations

from core.cfg import CfgEdgeKind, CfgNodeKind, build_cfg_graph


def _reachable(graph, start: str, goal: str) -> bool:
    seen: set[str] = set()
    stack = [start]
    while stack:
        cur = stack.pop()
        if cur == goal:
            return True
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(graph.successors(cur))
    return False


def test_r216_loop_else_no_false_bypass_of_else() -> None:
    """Exhaustion must go through else; no direct loop→join FALSE with else."""
    source = "for i in range(3):\n    x = i\nelse:\n    y = 1\n"
    graph = build_cfg_graph(source)
    loop = graph.nodes_of_kind(CfgNodeKind.LOOP)[0]
    join = next(n for n in graph.nodes.values() if n.label == "loop_join")
    else_id = next(n.id for n in graph.nodes.values() if n.kind == CfgNodeKind.BRANCH and n.label == "else")

    assert not any(e.src == loop.id and e.dst == join.id and e.kind == CfgEdgeKind.FALSE for e in graph.edges), (
        "loop→join FALSE bypasses else (R216)"
    )
    assert any(e.src == loop.id and e.dst == else_id and e.kind == CfgEdgeKind.ELSE for e in graph.edges)
    assert _reachable(graph, else_id, join.id)


def test_r216_loop_without_else_keeps_false_to_join() -> None:
    graph = build_cfg_graph("for i in range(3):\n    x = i\n")
    loop = graph.nodes_of_kind(CfgNodeKind.LOOP)[0]
    join = next(n for n in graph.nodes.values() if n.label == "loop_join")
    assert any(e.src == loop.id and e.dst == join.id and e.kind == CfgEdgeKind.FALSE for e in graph.edges)


def test_r216_break_still_skips_else_to_join() -> None:
    source = "for i in range(3):\n    break\nelse:\n    y = 1\n"
    graph = build_cfg_graph(source)
    breaks = graph.nodes_of_kind(CfgNodeKind.BREAK)
    join = next(n for n in graph.nodes.values() if n.label == "loop_join")
    assert breaks
    assert join.id in graph.successors(breaks[0].id)


def test_r216_nonexhaustive_match_has_false_to_join() -> None:
    source = "match x:\n    case 1:\n        a = 1\n    case 2:\n        b = 2\n"
    graph = build_cfg_graph(source)
    match = graph.nodes_of_kind(CfgNodeKind.MATCH)[0]
    join = next(n for n in graph.nodes.values() if n.label == "match_join")
    assert any(e.src == match.id and e.dst == join.id and e.kind == CfgEdgeKind.FALSE for e in graph.edges)
    assert any(e.kind == CfgEdgeKind.CASE for e in graph.edges)


def test_r216_exhaustive_wildcard_match_no_false_edge() -> None:
    source = "match x:\n    case 1:\n        a = 1\n    case _:\n        b = 2\n"
    graph = build_cfg_graph(source)
    match = graph.nodes_of_kind(CfgNodeKind.MATCH)[0]
    join = next(n for n in graph.nodes.values() if n.label == "match_join")
    assert not any(e.src == match.id and e.dst == join.id and e.kind == CfgEdgeKind.FALSE for e in graph.edges)


def test_r216_guarded_wildcard_still_needs_no_match() -> None:
    """``case _ if cond:`` is not irrefutable for exhaustiveness."""
    source = "match x:\n    case _ if x:\n        a = 1\n"
    graph = build_cfg_graph(source)
    match = graph.nodes_of_kind(CfgNodeKind.MATCH)[0]
    join = next(n for n in graph.nodes.values() if n.label == "match_join")
    assert any(e.src == match.id and e.dst == join.id and e.kind == CfgEdgeKind.FALSE for e in graph.edges)
