# -*- coding: utf-8 -*-
"""T022 — module/function/class docstrings are not duplicated as code blocks."""

from __future__ import annotations

from pathlib import Path

from tests.conformance.flow_serialize import getControlFlowFromMemory, serialize_control_flow


def test_docstrings_case_snapshot_semantics() -> None:
    source = (Path(__file__).parent / "cases" / "docstrings.py").read_text(encoding="utf-8")
    data = serialize_control_flow(source)
    assert data["docstring"] == "Module docstring."
    # Module docstring must not appear as a top-level CodeBlock
    kinds = [n["kind"] for n in data["nsuite"]]
    assert "CodeBlock" not in kinds or all(
        n.get("display") != '"""Module docstring."""' for n in data["nsuite"]
    )
    assert kinds[0] == "Function"
    assert data["nsuite"][0]["docstring"] == "Function docstring."
    assert all(c.get("display") != '"""Function docstring."""' for c in data["nsuite"][0].get("children", []))
    assert data["nsuite"][1]["kind"] == "Class"
    assert data["nsuite"][1]["docstring"] == "Class docstring."


def test_docstring_frag_exposes_line_spans_for_flow_ui() -> None:
    """flow UI scroll restore needs beginLine/endLine/body on docstring frags."""
    source = (Path(__file__).parent / "cases" / "docstrings.py").read_text(encoding="utf-8")
    cf = getControlFlowFromMemory(source)
    assert cf.docstring is not None
    assert cf.docstring.beginLine == 1
    assert cf.docstring.endLine >= 1
    assert cf.docstring.body.getLineRange() == (cf.docstring.beginLine, cf.docstring.endLine)
    assert cf.docstring.body.getAbsPosRange() == (cf.docstring.begin, cf.docstring.end)

    func = cf.nsuite[0]
    assert func.docstring is not None
    assert func.docstring.beginLine >= 2
    assert func.docstring.body.beginLine == func.docstring.beginLine


def test_match_kinds() -> None:
    match_src = (Path(__file__).parent / "cases" / "match_case.py").read_text(encoding="utf-8")
    data = serialize_control_flow(match_src)
    func = data["nsuite"][0]
    assert func["kind"] == "Function"
    match_nodes = [c for c in func.get("children", []) if c.get("kind") == "Match"]
    assert match_nodes
    cases = [p for p in match_nodes[0].get("children", []) if p.get("kind") == "Case" or p.get("role") == "part"]
    assert cases


def test_try_star_kind() -> None:
    import sys

    if sys.version_info < (3, 11):
        import pytest

        pytest.skip("except* requires Python 3.11+")
    src = (Path(__file__).parent / "cases" / "except_star.py").read_text(encoding="utf-8")
    data = serialize_control_flow(src)
    func = data["nsuite"][0]
    try_nodes = [c for c in func.get("children", []) if c.get("kind") == "TryStar"]
    assert try_nodes
