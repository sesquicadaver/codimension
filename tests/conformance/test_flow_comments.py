# -*- coding: utf-8 -*-
"""T025–T027 flow grammar / comments / comprehensions gates."""

from __future__ import annotations

from pathlib import Path

from tests.conformance.flow_serialize import getControlFlowFromMemory, serialize_control_flow

CASES = Path(__file__).parent / "cases"


def test_comments_leading_side_independent() -> None:
    source = (CASES / "comments.py").read_text(encoding="utf-8")
    data = serialize_control_flow(source)
    # First code stmt has leading + side comments
    code_nodes = [n for n in data["nsuite"] if n.get("kind") == "CodeBlock"]
    assert code_nodes
    first = code_nodes[0]
    assert first.get("leadingComment")
    assert "# leading comment" in first["leadingComment"]
    assert first.get("sideComment")
    assert "# side comment" in first["sideComment"]
    # Independent comment becomes its own Comment fragment
    kinds = [n["kind"] for n in data["nsuite"]]
    assert "Comment" in kinds


def test_cml_leading_attached() -> None:
    source = (CASES / "cml.py").read_text(encoding="utf-8")
    data = serialize_control_flow(source)
    code = next(n for n in data["nsuite"] if n.get("kind") == "CodeBlock")
    assert code.get("leadingCML")
    assert code["leadingCML"][0]["recordType"] == "rt"


def test_async_for_with_flags() -> None:
    source = (CASES / "async_loops.py").read_text(encoding="utf-8")
    data = serialize_control_flow(source)
    async_fn = data["nsuite"][0]
    assert async_fn["kind"] == "Function"
    assert async_fn.get("isAsync") is True
    async_for = next(c for c in async_fn["children"] if c.get("kind") == "For")
    assert async_for.get("isAsync") is True
    async_with = next(c for c in async_for["children"] if c.get("kind") == "With")
    assert async_with.get("isAsync") is True
    sync_fn = data["nsuite"][1]
    sync_for = next(c for c in sync_fn["children"] if c.get("kind") == "For")
    assert sync_for.get("isAsync") is not True
    sync_with = next(c for c in sync_for["children"] if c.get("kind") == "With")
    assert sync_with.get("isAsync") is not True
    assert sync_with.get("withItems")


def test_comprehensions_flagged_full_span() -> None:
    source = (CASES / "comprehensions.py").read_text(encoding="utf-8")
    data = serialize_control_flow(source)
    comps = [n for n in data["nsuite"] if n.get("isComprehension")]
    assert len(comps) >= 3
    for node in comps:
        assert node["end"] > node["begin"]
        assert node["display"]
        assert source[node["begin"] : node["end"]] == node["display"]


def test_shebang_and_encoding_recovered(tmp_path: Path) -> None:
    from codimension.parsers import flow_ast

    path = tmp_path / "enc.py"
    path.write_bytes(b"#!/usr/bin/env python3\n# -*- coding: latin-1 -*-\nx = 1\n")
    cf = flow_ast.getControlFlowFromFile(str(path))
    assert cf.bangLine is not None
    assert cf.encodingLine is not None


def test_if_header_side_comment_attached() -> None:
    source = "if x:  # note\n    pass\n"
    cf = getControlFlowFromMemory(source)
    assert len(cf.nsuite) == 1
    if_frag = cf.nsuite[0]
    assert if_frag.kind == 19  # IF_FRAGMENT
    # Side may land on If or its first part (header)
    side = if_frag.sideComment or (if_frag.parts[0].sideComment if if_frag.parts else None)
    assert side is not None
    assert "# note" in side.getDisplayValue()
    assert not any(getattr(n, "kind", None) == 3 for n in cf.nsuite)  # no leaked Comment


def test_except_header_side_comment_attached() -> None:
    source = "try:\n    f()\nexcept ValueError:  # err\n    pass\n"
    cf = getControlFlowFromMemory(source)
    try_frag = cf.nsuite[0]
    assert try_frag.exceptParts
    side = try_frag.exceptParts[0].sideComment
    assert side is not None
    assert "# err" in side.getDisplayValue()


def test_decorator_leading_comment_attached() -> None:
    source = "# deco comment\n@deco\ndef f():\n    pass\n"
    cf = getControlFlowFromMemory(source)
    fn = cf.nsuite[0]
    assert fn.kind == 7
    leading = None
    if fn.decorators and fn.decorators[0].leadingComment:
        leading = fn.decorators[0].leadingComment
    elif fn.leadingComment:
        leading = fn.leadingComment
    assert leading is not None
    assert "# deco comment" in leading.getDisplayValue()
    assert not any(getattr(n, "kind", None) == 3 for n in fn.nsuite)


def test_else_finally_side_comments() -> None:
    source = (
        "try:\n"
        "    f()\n"
        "except Exception:\n"
        "    g()\n"
        "else:  # e\n"
        "    h()\n"
        "finally:  # f\n"
        "    i()\n"
    )
    cf = getControlFlowFromMemory(source)
    try_frag = cf.nsuite[0]
    assert try_frag.elsePart is not None
    assert try_frag.elsePart.sideComment is not None
    assert "# e" in try_frag.elsePart.sideComment.getDisplayValue()
    assert try_frag.finallyPart is not None
    assert try_frag.finallyPart.sideComment is not None
    assert "# f" in try_frag.finallyPart.sideComment.getDisplayValue()


def test_case_span_includes_header() -> None:
    source = (CASES / "match_case.py").read_text(encoding="utf-8")
    data = serialize_control_flow(source)
    func = data["nsuite"][0]
    match = next(c for c in func["children"] if c.get("kind") == "Match")
    case = next(c for c in match["children"] if c.get("kind") == "Case" or c.get("role") == "part")
    assert case["display"].startswith("case ")
    slice_txt = source[case["begin"] : case["end"]]
    assert slice_txt.lstrip().startswith("case"), slice_txt
    # Must not be body-only
    assert 'return "zero"' != slice_txt
