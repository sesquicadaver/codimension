# -*- coding: utf-8 -*-
"""Unit tests for T072 AST import gate (bypass resistance)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "scripts" / "check_package_relative_imports.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("check_package_relative_imports", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_gate_catches_second_name_in_import_list(tmp_path: Path) -> None:
    gate = _load_gate()
    path = tmp_path / "bad.py"
    path.write_text("import os, parsers.foo\n", encoding="utf-8")
    failures = gate.check_file(path)
    assert failures and "parsers" in failures[0]


def test_gate_rejects_nested_import_inside_except(tmp_path: Path) -> None:
    gate = _load_gate()
    path = tmp_path / "nested.py"
    path.write_text(
        "try:\n    pass\nexcept ImportError:\n    def f():\n        import parsers.foo\n",
        encoding="utf-8",
    )
    failures = gate.check_file(path)
    assert failures and "parsers" in failures[0]


def test_gate_allows_direct_except_importerror_fallback(tmp_path: Path) -> None:
    gate = _load_gate()
    path = tmp_path / "ok.py"
    path.write_text(
        "try:\n    from .x import y\nexcept ImportError:\n    from parsers.x import y\n",
        encoding="utf-8",
    )
    assert gate.check_file(path) == []
