# -*- coding: utf-8 -*-
"""R131: populate SymbolIndex from brief_ast with accuracy checks."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import parsers  # noqa: E402,F401
import pytest
from core.symbol_index import SymbolKind

_CODIM = Path(__file__).resolve().parents[1] / "codimension"

SAMPLE = '''\
"""mod doc"""
import os
from typing import List

X = 1

def top(a):
    def nested():
        return a
    return nested

class Outer:
    FLAG = True

    def meth(self):
        self.value = 2

    class Inner:
        def inner_m(self):
            pass
'''


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


def test_index_source_known_defs():
    from utils.symbol_index_brief import index_source

    records = index_source(SAMPLE, "sample.py")
    by_qn = {r.qualname: r for r in records}

    assert "os" in by_qn and by_qn["os"].kind is SymbolKind.IMPORT
    assert "List" in by_qn and by_qn["List"].extras.get("from") == "typing"
    assert "X" in by_qn and by_qn["X"].kind is SymbolKind.VARIABLE
    assert "top" in by_qn and by_qn["top"].kind is SymbolKind.FUNCTION
    assert "top.nested" in by_qn
    assert "Outer" in by_qn and by_qn["Outer"].kind is SymbolKind.CLASS
    assert "Outer.FLAG" in by_qn and by_qn["Outer.FLAG"].kind is SymbolKind.ATTRIBUTE
    assert "Outer.meth" in by_qn and by_qn["Outer.meth"].kind is SymbolKind.METHOD
    assert "Outer.value" in by_qn  # instance attribute
    assert "Outer.Inner" in by_qn
    assert "Outer.Inner.inner_m" in by_qn and by_qn["Outer.Inner.inner_m"].kind is SymbolKind.METHOD

    # Half-open span covers the name characters in source.
    top = by_qn["top"]
    assert SAMPLE[top.span.start : top.span.end] == "top"
    outer = by_qn["Outer"]
    assert SAMPLE[outer.span.start : outer.span.end] == "Outer"


def test_build_symbol_index_from_paths(tmp_path: Path):
    from utils.symbol_index_brief import build_symbol_index

    f1 = tmp_path / "a.py"
    f2 = tmp_path / "b.py"
    f1.write_text("def a():\n    pass\n", encoding="utf-8")
    f2.write_text("class B:\n    pass\n", encoding="utf-8")
    seen: list[str] = []

    def on_file(path: str, records) -> None:
        seen.append(path)
        assert len(records) >= 1

    index = build_symbol_index([str(f1), str(f2)], on_file=on_file)
    assert len(index.by_name("a")) == 1
    assert len(index.by_name("B")) == 1
    assert seen == [str(f1), str(f2)]


def test_build_symbol_index_from_sources_callback():
    from utils.symbol_index_brief import build_symbol_index_from_sources

    index = build_symbol_index_from_sources([("m.py", "def f():\n    return 1\n")])
    assert [r.qualname for r in index] == ["f"]


def test_parse_error_yields_empty():
    from utils.symbol_index_brief import index_source

    assert index_source("def (\n", "bad.py") == []
