# -*- coding: utf-8 -*-
"""R151: headless AI context packer (SymbolIndex + CFG slice)."""

from __future__ import annotations

import json

import pytest
from core.ai_context import (
    AI_CONTEXT_FORMAT,
    build_ai_context,
    build_ai_context_from_source,
    slice_cfg_for_symbol,
)
from core.cfg import CfgNodeKind, build_cfg_graph
from core.symbol_index import SymbolIndex, SymbolKind, build_symbol


def test_build_ai_context_from_source_packs_cfg_and_excerpt() -> None:
    source = "def helper():\n    return 0\n\ndef target(x):\n    if x:\n        return 1\n    return 2\n"
    pack = build_ai_context_from_source(source, "target", file="mod.py")
    assert pack.format == AI_CONTEXT_FORMAT
    assert pack.symbol.name == "target"
    assert pack.cfg_slice is not None
    assert pack.cfg_slice.root_id
    kinds = {n.kind for n in pack.cfg_slice.nodes}
    assert CfgNodeKind.FUNCTION in kinds
    assert CfgNodeKind.IF in kinds or CfgNodeKind.RETURN in kinds
    assert "def target" in pack.source_excerpt
    assert "helper" not in pack.source_excerpt
    payload = pack.to_dict()
    assert payload["cfg_slice"]["nodes"]
    # Must be JSON-serializable (offline AI tooling).
    json.dumps(payload)


def test_slice_cfg_for_symbol_isolates_function() -> None:
    source = "def a():\n    return 1\n\ndef b():\n    return 2\n"
    graph = build_cfg_graph(source)
    slice_b = slice_cfg_for_symbol(graph, name="b", kind=SymbolKind.FUNCTION, line=4)
    assert slice_b is not None
    labels = {n.label for n in slice_b.nodes if n.kind == CfgNodeKind.FUNCTION}
    assert labels == {"b"}


def test_build_ai_context_includes_definitions_and_references() -> None:
    index = SymbolIndex(
        [
            build_symbol("Foo", SymbolKind.CLASS, "a.py", 0, 3, line=1),
            build_symbol("Foo", SymbolKind.IMPORT, "b.py", 0, 3, line=1),
            build_symbol("bar", SymbolKind.METHOD, "a.py", 4, 7, container="Foo", line=2),
        ]
    )
    sources = {"a.py": "class Foo:\n    def bar(self):\n        return 1\n", "b.py": "from a import Foo\n"}
    pack = build_ai_context(index, "Foo", sources, file="a.py", kind=SymbolKind.CLASS)
    assert pack.definitions[0].kind is SymbolKind.CLASS
    assert pack.references
    assert any(r.name == "bar" for r in pack.related)
    assert pack.cfg_slice is not None


def test_missing_definition_raises() -> None:
    with pytest.raises(ValueError, match="no definition"):
        build_ai_context(SymbolIndex(), "missing", {})


def test_missing_source_notes_without_cfg() -> None:
    index = SymbolIndex([build_symbol("f", SymbolKind.FUNCTION, "x.py", 0, 1, line=1)])
    pack = build_ai_context(index, "f", {})
    assert pack.cfg_slice is None
    assert any("missing source" in n for n in pack.notes)
