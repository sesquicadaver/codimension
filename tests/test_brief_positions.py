# -*- coding: utf-8 -*-
"""B04: brief class/function keyword, name, colon + assignment identifier positions."""

from __future__ import annotations

from parsers.brief_ast import getBriefModuleInfoFromMemory
from parsers.source_spans import SourceIndex, TokenIndex


def test_function_header_separates_keyword_name_colon():
    """Identifier must not equal ``def``; colon is header, not body end."""
    src = "def greet(\n    name: str,\n) -> str:\n    return name\n"
    info = getBriefModuleInfoFromMemory(src)
    assert info.isOK
    fn = next(f for f in info.functions if f.name == "greet")
    assert fn.keywordLine == 1
    assert fn.keywordPos == 1
    assert src[fn.absPosition : fn.absPosition + len("greet")] == "greet"
    assert fn.line == 1
    assert fn.pos == src.index("greet") + 1
    assert fn.colonLine == 3
    assert src.splitlines()[fn.colonLine - 1][fn.colonPos - 1] == ":"
    assert fn.colonLine < 4  # body starts on line 4


def test_async_and_class_headers():
    src = "async def fetch():\n    return 1\n\nclass Box(\n    object,\n):\n    pass\n"
    info = getBriefModuleInfoFromMemory(src)
    fn = next(f for f in info.functions if f.name == "fetch")
    assert fn.isAsync
    assert fn.keywordPos == 1
    assert src[fn.absPosition : fn.absPosition + 5] == "fetch"
    assert fn.colonLine == 1

    cls = next(c for c in info.classes if c.name == "Box")
    assert src[cls.absPosition : cls.absPosition + 3] == "Box"
    assert cls.keywordLine == 4
    assert cls.colonLine == 6
    assert src.splitlines()[cls.colonLine - 1][cls.colonPos - 1] == ":"


def test_assignment_and_import_identifier_positions():
    src = (
        "alpha, beta = 1, 2\n"
        "import pkg as alias\n"
        "from mod import item as renamed\n"
        "\n"
        "class Holder:\n"
        "    left, right = 0, 1\n"
        "\n"
        "    def __init__(self):\n"
        "        self.state = 3\n"
    )
    info = getBriefModuleInfoFromMemory(src)
    index = SourceIndex.build(src)

    g_alpha = next(g for g in info.globals if g.name == "alpha")
    g_beta = next(g for g in info.globals if g.name == "beta")
    assert src[g_alpha.absPosition : g_alpha.absPosition + 5] == "alpha"
    assert src[g_beta.absPosition : g_beta.absPosition + 4] == "beta"
    assert g_alpha.absPosition != g_beta.absPosition

    imp = next(i for i in info.imports if i.name == "pkg")
    assert src[imp.absPosition : imp.absPosition + 3] == "pkg"
    what = next(w for w in next(i for i in info.imports if i.name == "mod").what if w.name == "item")
    assert src[what.absPosition : what.absPosition + 4] == "item"

    holder = next(c for c in info.classes if c.name == "Holder")
    left = next(a for a in holder.classAttributes if a.name == "left")
    right = next(a for a in holder.classAttributes if a.name == "right")
    assert src[left.absPosition : left.absPosition + 4] == "left"
    assert src[right.absPosition : right.absPosition + 5] == "right"

    state = next(a for a in holder.instanceAttributes if a.name == "state")
    assert src[state.absPosition : state.absPosition + 5] == "state"
    # Attribute identifier must not point at ``self``
    assert src[state.absPosition : state.absPosition + 4] != "self"
    ln, col = index.line_col_from_abs(state.absPosition)
    assert ln == state.line and col == state.pos


def test_encoding_cookie_on_second_line_after_false_coding_word():
    """D05: a non-cookie 'coding' on line 1 must not skip a valid line-2 cookie."""
    src = "# this mentions coding without a cookie\n# -*- coding: latin-1 -*-\nx = 1\n"
    info = getBriefModuleInfoFromMemory(src)
    assert info.isOK
    assert info.encoding is not None
    assert info.encoding.name == "latin-1"
    assert info.encoding.line == 2


def test_token_index_suite_header_helper():
    src = "def f(x: int = 1) -> None:\n    pass\n"
    index = SourceIndex.build(src)
    tokens = TokenIndex.build(src)
    import ast

    tree = ast.parse(src)
    resolved = tokens.suite_header_positions(index, tree.body[0], "f", "def")
    assert resolved is not None
    name_ln, name_pos, name_abs, kw_ln, kw_pos, colon_ln, colon_pos = resolved
    assert (kw_ln, kw_pos) == (1, 1)
    assert src[name_abs : name_abs + 1] == "f"
    assert (name_ln, name_pos) == (1, 5)
    assert src.splitlines()[colon_ln - 1][colon_pos - 1] == ":"
