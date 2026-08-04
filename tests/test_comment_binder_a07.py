# -*- coding: utf-8 -*-
"""A07: tokenize character columns + nested trailing comment ownership."""

from __future__ import annotations

from parsers.comment_binder import collect_token_comments
from parsers.flow_ast import getControlFlowFromMemory
from parsers.source_spans import SourceIndex


def test_unicode_side_comment_absolute_span():
    """tokenize columns are characters — must not go through UTF-8 byte converter."""
    src = 'значення = "тест"  # коментар\n'
    index = SourceIndex.build(src)
    comments, warnings = collect_token_comments(src, index)
    assert not warnings
    assert len(comments) == 1
    c = comments[0]
    assert src[c.begin : c.end] == "# коментар"
    assert c.text == "# коментар"


def test_unicode_side_comment_attached_to_codeblock():
    src = 'значення = "тест"  # коментар\n'
    cf = getControlFlowFromMemory(src)
    assert len(cf.nsuite) == 1
    frag = cf.nsuite[0]
    assert frag.sideComment is not None
    assert "# коментар" in frag.sideComment.getDisplayValue()
    begin, end = frag.sideComment.getAbsPosRange()
    assert src[begin:end] == "# коментар"


def test_nested_trailing_comment_stays_in_function():
    src = """def process():
    execute()
    # comment about process

next_step()
"""
    cf = getControlFlowFromMemory(src)
    assert len(cf.nsuite) == 2
    fn, nxt = cf.nsuite
    assert fn.kind == 7  # FUNCTION
    kinds = [x.kind for x in fn.nsuite]
    assert 3 in kinds  # COMMENT_FRAGMENT inside function
    displays = [x.getDisplayValue() for x in fn.nsuite if x.kind == 3]
    assert any("# comment about process" in d for d in displays)
    # Must not leak as module-level independent before next_step
    assert not any(getattr(x, "kind", None) == 3 for x in cf.nsuite)


def test_dedented_comment_not_pulled_into_function():
    src = """def process():
    execute()

# module comment
next_step()
"""
    cf = getControlFlowFromMemory(src)
    fn = cf.nsuite[0]
    assert not any(getattr(x, "kind", None) == 3 for x in fn.nsuite)
    # Module comment becomes leading of next_step or independent at module
    nxt = cf.nsuite[-1]
    leading = getattr(nxt, "leadingComment", None)
    module_comments = [x for x in cf.nsuite if getattr(x, "kind", None) == 3]
    assert (leading is not None and "# module comment" in leading.getDisplayValue()) or any(
        "# module comment" in x.getDisplayValue() for x in module_comments
    )
