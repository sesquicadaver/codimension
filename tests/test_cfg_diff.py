# -*- coding: utf-8 -*-
"""R142: structural CFG graph diff."""

from __future__ import annotations

from pathlib import Path

from core.cfg import CfgNodeKind, build_cfg_graph
from core.cfg_diff import diff_cfg_graphs, diff_cfg_sources, node_key

CASES = Path(__file__).resolve().parent / "conformance" / "cases"


def test_identical_sources_empty_diff() -> None:
    src = "def f(x):\n    if x:\n        return 1\n    return 0\n"
    diff = diff_cfg_sources(src, src)
    assert diff.empty
    assert diff.summary() == {
        "added_nodes": 0,
        "removed_nodes": 0,
        "changed_nodes": 0,
        "added_edges": 0,
        "removed_edges": 0,
    }


def test_added_function_shows_added_nodes() -> None:
    before = "x = 1\n"
    after = "x = 1\n\ndef f():\n    return 2\n"
    diff = diff_cfg_sources(before, after)
    assert not diff.empty
    assert diff.added_nodes
    kinds = {n.kind for n in diff.added_nodes}
    assert CfgNodeKind.FUNCTION in kinds
    assert CfgNodeKind.RETURN in kinds
    assert not diff.removed_nodes


def test_removed_branch_shows_removed_nodes() -> None:
    before = "def f(x):\n    if x:\n        return 1\n    return 0\n"
    after = "def f(x):\n    return 0\n"
    diff = diff_cfg_sources(before, after)
    assert diff.removed_nodes
    kinds = {n.kind for n in diff.removed_nodes}
    assert CfgNodeKind.IF in kinds or CfgNodeKind.RETURN in kinds


def test_line_shift_is_changed_not_add_remove() -> None:
    before = "def f():\n    return 1\n"
    after = "\n\ndef f():\n    return 1\n"
    diff = diff_cfg_sources(before, after)
    # Soft identity pairs function/return across line shift.
    assert diff.changed_nodes
    soft = {(c.before.kind, c.before.label) for c in diff.changed_nodes}
    assert (CfgNodeKind.FUNCTION, "f") in soft


def test_fixture_pair_nested_vs_match() -> None:
    nested = (CASES / "nested_scopes.py").read_text(encoding="utf-8")
    match = (CASES / "match_case.py").read_text(encoding="utf-8")
    diff = diff_cfg_sources(nested, match)
    assert not diff.empty
    assert diff.added_nodes or diff.removed_nodes or diff.changed_nodes


def test_diff_graphs_direct_and_node_key_stable() -> None:
    g1 = build_cfg_graph("a = 1\n")
    g2 = build_cfg_graph("a = 1\n")
    assert diff_cfg_graphs(g1, g2).empty
    code1 = [n for n in g1.nodes.values() if n.kind == CfgNodeKind.CODE][0]
    code2 = [n for n in g2.nodes.values() if n.kind == CfgNodeKind.CODE][0]
    # Same content → same key even if allocation ids differ.
    assert node_key(code1) == node_key(code2)
