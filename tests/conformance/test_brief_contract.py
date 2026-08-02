# -*- coding: utf-8 -*-
"""T006 — brief model assertion helpers + minimal smoke."""

from __future__ import annotations

import pytest

from tests.conformance.brief_asserts import (
    argument_defaults,
    class_attribute_names,
    class_method_names,
    function_names,
    global_names,
    instance_attribute_names,
    parse_brief,
)


def test_helpers_smoke_known_good() -> None:
    """Minimal sync function that current brief_ast already handles."""
    info = parse_brief("def hello():\n    return 1\n")
    assert info.isOK
    assert function_names(info) == ["hello"]
    assert function_names(info, async_only=True) == []
    assert argument_defaults(info, "hello") == {}


def test_async_defs_in_brief_model() -> None:
    """T010: top-level / method / nested async def appear with isAsync."""
    from pathlib import Path

    source = (Path(__file__).parent / "cases" / "async_defs.py").read_text(encoding="utf-8")
    info = parse_brief(source)
    assert "top_level" in function_names(info, async_only=True)
    assert "method" in class_method_names(info, "Service")
    # nested async inside method
    svc = next(c for c in info.classes if c.name == "Service")
    method = next(f for f in svc.functions if f.name == "method")
    nested_names = [f.name for f in method.functions]
    assert "nested" in nested_names
    assert all(f.isAsync for f in method.functions if f.name == "nested")
    assert all(f.isAsync for f in info.functions if f.name == "top_level")
    assert all(f.isAsync for f in svc.functions if f.name == "method")


def test_defaults_mapped_correctly() -> None:
    """T011: defaults bind to the matching arguments."""
    info = parse_brief("def f(a=1, b=2):\n    return a + b\n")
    assert argument_defaults(info, "f") == {"a": "1", "b": "2"}


def test_arg_kinds_posonly_kwonly() -> None:
    """T012: positional-only, vararg, keyword-only, kwarg."""
    from pathlib import Path

    source = (Path(__file__).parent / "cases" / "arg_kinds.py").read_text(encoding="utf-8")
    info = parse_brief(source)
    names = [a.name for a in info.functions[0].arguments]
    assert names == ["a", "/", "b", "*args", "c", "**kwargs"]
    defaults = argument_defaults(info, "f")
    assert defaults["c"] == "3"
    assert defaults["a"] is None
    assert defaults["b"] is None


def test_defaults_case_g_mixed() -> None:
    """T011/T012: mixed pos-only / kw-only defaults from defaults.py case."""
    from pathlib import Path

    source = (Path(__file__).parent / "cases" / "defaults.py").read_text(encoding="utf-8")
    info = parse_brief(source)
    assert argument_defaults(info, "f") == {"a": "1", "b": "2"}
    g = argument_defaults(info, "g")
    assert g["a"] is None
    assert g["b"] == "2"
    assert g["c"] == "3"
    assert g["d"] == "4"
    assert g["e"] == "5"
    g_names = [a.name for a in next(fn for fn in info.functions if fn.name == "g").arguments]
    assert "/" in g_names
    assert "*" in g_names


def test_instance_attrs_self_only() -> None:
    """T013: instance attrs are self.x / cls.x, not local Names."""
    from pathlib import Path

    source = (Path(__file__).parent / "cases" / "instance_attrs.py").read_text(encoding="utf-8")
    info = parse_brief(source)
    attrs = instance_attribute_names(info, "Service")
    assert "state" in attrs
    assert "temporary" not in attrs


def test_assigns_ann_unpack_chained() -> None:
    """T014: AnnAssign, AugAssign, unpacking, chained assignment."""
    from pathlib import Path

    source = (Path(__file__).parent / "cases" / "assigns.py").read_text(encoding="utf-8")
    info = parse_brief(source)
    globals_ = set(global_names(info))
    assert {"count", "total", "x", "y", "a", "b", "first", "rest"} <= globals_
    class_attrs = set(class_attribute_names(info, "Box"))
    assert {"size", "width", "height", "left", "right"} <= class_attrs
    inst = set(instance_attribute_names(info, "Box"))
    assert {"color", "x", "y", "hits"} <= inst


def test_unicode_brief_spans() -> None:
    """T017: absPosition uses character indices (Cyrillic-safe)."""
    from pathlib import Path

    from parsers.source_spans import SourceIndex

    source = (Path(__file__).parent / "cases" / "unicode_spans.py").read_text(encoding="utf-8")
    info = parse_brief(source)
    index = SourceIndex.build(source)
    # Find global 'привіт'
    g = next(x for x in info.globals if x.name == "привіт")
    # Node for first assign
    import ast

    tree = ast.parse(source)
    begin, end, *_ = index.node_span(tree.body[0])
    assert g.absPosition == begin
    assert source[begin:end].startswith("привіт")


def test_tokenize_open_encoding(tmp_path) -> None:
    """T016: getBriefModuleInfoFromFile respects PEP 263 via tokenize.open."""
    from parsers.brief_ast import getBriefModuleInfoFromFile

    target = tmp_path / "encoding_latin1.py"
    target.write_bytes(
        b"# -*- coding: latin-1 -*-\n"
        b'name = "caf\xe9"\n'
    )
    info = getBriefModuleInfoFromFile(str(target))
    assert info.isOK
    assert "name" in [g.name for g in info.globals]


def test_nested_scopes_control_flow() -> None:
    """T015: nested funcs and self.attr inside if/for/try/with."""
    from pathlib import Path

    source = (Path(__file__).parent / "cases" / "nested_scopes.py").read_text(encoding="utf-8")
    info = parse_brief(source)
    assert "flag" in instance_attribute_names(info, "Outer")
    methods = class_method_names(info, "Outer")
    assert "method" in methods
    outer = next(c for c in info.classes if c.name == "Outer")
    method = next(f for f in outer.functions if f.name == "method")
    nested = {f.name for f in method.functions}
    assert {"nested", "anested"} <= nested
