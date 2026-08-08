# -*- coding: utf-8 -*-
"""R132: SymbolIndex find_definitions / find_references."""

from __future__ import annotations

from core.symbol_index import SymbolIndex, SymbolKind, build_symbol
from utils.symbol_index_brief import build_symbol_index_from_sources


def test_find_definitions_excludes_imports():
    index = SymbolIndex(
        [
            build_symbol("Foo", SymbolKind.CLASS, "a.py", 0, 3, line=1),
            build_symbol("Foo", SymbolKind.IMPORT, "b.py", 0, 3, line=2),
            build_symbol("Foo", SymbolKind.FUNCTION, "c.py", 0, 3, line=3, container="pkg"),
        ]
    )
    defs = index.find_definitions("Foo")
    assert [r.file for r in defs] == ["a.py", "c.py"]
    assert index.find_definitions("Foo", kind=SymbolKind.CLASS)[0].file == "a.py"
    assert index.find_definitions("Foo", qualname="pkg.Foo")[0].file == "c.py"
    assert index.find_definitions("Foo", file="a.py")[0].kind is SymbolKind.CLASS


def test_find_references_imports_and_role():
    index = SymbolIndex(
        [
            build_symbol("Foo", SymbolKind.CLASS, "a.py", 0, 3, line=1),
            build_symbol("Foo", SymbolKind.IMPORT, "b.py", 0, 3, line=2),
            build_symbol(
                "Foo",
                SymbolKind.UNKNOWN,
                "c.py",
                0,
                3,
                line=4,
                extras={"role": "reference"},
            ),
        ]
    )
    refs = index.find_references("Foo")
    assert [r.file for r in refs] == ["b.py", "c.py"]
    assert index.find_references("Foo", file="b.py")[0].kind is SymbolKind.IMPORT


def test_queries_on_brief_populated_index():
    source = "from typing import List\n\nclass ListWrap:\n    pass\n"
    index = build_symbol_index_from_sources([("m.py", source)])
    defs = index.find_definitions("ListWrap")
    assert len(defs) == 1 and defs[0].kind is SymbolKind.CLASS
    refs = index.find_references("List")
    assert len(refs) == 1 and refs[0].kind is SymbolKind.IMPORT
    assert defs[0].line is not None
