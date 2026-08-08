# -*- coding: utf-8 -*-
"""R130: SymbolIndex schema (name, kind, file, half-open span, container)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from core.symbol_index import (
    SourceSpan,
    SymbolIndex,
    SymbolKind,
    SymbolRecord,
    build_symbol,
)


def test_source_span_half_open():
    span = SourceSpan(10, 15)
    assert span.length == 5
    assert span.contains(10)
    assert span.contains(14)
    assert not span.contains(15)
    assert span.overlaps(SourceSpan(14, 20))
    assert not span.overlaps(SourceSpan(15, 20))


def test_source_span_rejects_invalid():
    with pytest.raises(ValueError, match="start"):
        SourceSpan(-1, 0)
    with pytest.raises(ValueError, match="end"):
        SourceSpan(5, 4)


def test_symbol_record_fields_and_qualname():
    rec = build_symbol(
        "foo",
        SymbolKind.METHOD,
        "pkg/mod.py",
        100,
        103,
        container="pkg.mod.MyClass",
    )
    assert rec.name == "foo"
    assert rec.kind is SymbolKind.METHOD
    assert rec.file == "pkg/mod.py"
    assert rec.span == SourceSpan(100, 103)
    assert rec.container == "pkg.mod.MyClass"
    assert rec.qualname == "pkg.mod.MyClass.foo"


def test_symbol_record_module_level_qualname():
    rec = SymbolRecord(
        name="Helper",
        kind=SymbolKind.CLASS,
        file="/abs/a.py",
        span=SourceSpan(0, 6),
    )
    assert rec.container is None
    assert rec.qualname == "Helper"


def test_symbol_record_rejects_empty_name_or_file():
    with pytest.raises(ValueError, match="name"):
        build_symbol("", SymbolKind.FUNCTION, "a.py", 0, 1)
    with pytest.raises(ValueError, match="file"):
        build_symbol("f", SymbolKind.FUNCTION, "", 0, 1)


def test_symbol_index_add_and_filters():
    index = SymbolIndex()
    index.add(build_symbol("A", "class", "a.py", 0, 1))
    index.add(build_symbol("f", SymbolKind.FUNCTION, "a.py", 10, 11, container="A"))
    index.add(build_symbol("f", SymbolKind.FUNCTION, "b.py", 0, 1))
    assert len(index) == 3
    assert [r.name for r in index.by_file("a.py")] == ["A", "f"]
    assert len(index.by_name("f")) == 2
    assert len(index.by_kind(SymbolKind.CLASS)) == 1
    assert len(index.by_container("A")) == 1
    assert len(index.by_container(None)) == 2
    assert all(isinstance(r, SymbolRecord) for r in index.symbols())


def test_symbol_index_extend_and_clear():
    index = SymbolIndex([build_symbol("x", SymbolKind.VARIABLE, "v.py", 0, 1)])
    index.extend([build_symbol("y", SymbolKind.VARIABLE, "v.py", 2, 3)])
    assert len(index) == 2
    index.clear()
    assert len(index) == 0


def test_core_symbol_index_import_without_qt():
    """Gate: importing core.symbol_index must not pull Qt."""
    root = Path(__file__).resolve().parents[1]
    code = (
        "import sys\n"
        f"sys.path.insert(0, {str(root / 'codimension')!r})\n"
        f"sys.path.insert(0, {str(root)!r})\n"
        "assert 'PyQt5' not in sys.modules\n"
        "from core.symbol_index import SymbolIndex, SymbolRecord, SourceSpan\n"
        "assert 'PyQt5' not in sys.modules\n"
        "print('ok')\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)
    assert "ok" in proc.stdout
