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
