# -*- coding: utf-8 -*-
"""T004 — conformance fixtures load skeleton (ast.parse only)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

CASES_DIR = Path(__file__).resolve().parent / "cases"


def _case_files() -> list[Path]:
    return sorted(p for p in CASES_DIR.glob("*.py") if p.is_file())


@pytest.mark.parametrize("case_path", _case_files(), ids=lambda p: p.name)
def test_case_loads_with_ast_parse(case_path: Path) -> None:
    """Every conformance fixture must be valid Python for the running interpreter."""
    import sys

    # except* / TryStar requires Python 3.11+
    if case_path.name == "except_star.py" and sys.version_info < (3, 11):
        pytest.skip("except* requires Python 3.11+")
    source = case_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(case_path))
    assert isinstance(tree, ast.Module)
    assert tree.body, f"empty module body in {case_path.name}"


def test_expected_case_inventory() -> None:
    """Guard against accidental empty cases/ directory."""
    names = {p.name for p in _case_files()}
    required = {
        "async_defs.py",
        "defaults.py",
        "instance_attrs.py",
        "arg_kinds.py",
        "unicode_spans.py",
        "match_case.py",
        "except_star.py",
        "docstrings.py",
        "comments.py",
        "nested_scopes.py",
        "assigns.py",
        "encoding_latin1.py",
    }
    missing = required - names
    assert not missing, f"missing conformance cases: {sorted(missing)}"
