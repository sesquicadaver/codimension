# -*- coding: utf-8 -*-
"""B05/D04 CML clustering, B06 case token, D06 multiline header side comments."""

from __future__ import annotations

from parsers.comment_binder import _build_clusters, collect_token_comments
from parsers.flow_ast import getControlFlowFromMemory
from parsers.source_spans import SourceIndex


def test_cml_not_swallowed_by_ordinary_comment_cluster():
    """D04/B05: ordinary comment must not absorb a following CML head."""
    src = '# ordinary comment\n# cml 1 rt text="note"\nvalue = 1\n'
    cf = getControlFlowFromMemory(src)
    code = next(x for x in cf.nsuite if getattr(x, "kind", None) == 6)
    assert code.leadingCMLComments, "CML must attach as leading CML"
    assert code.leadingCMLComments[0].recordType == "rt"
    leading = code.leadingComment
    assert leading is not None
    assert "# ordinary comment" in leading.getDisplayValue()


def test_separate_cml_records_and_indent_scopes():
    """D04/B05: each CML head is its own cluster; indent breaks grouping."""
    src = '# cml 1 gb id="x"\n# cml 1 ge id="x"\nif condition:\n    # inner\n    pass\n# outer\nnext_step()\n'
    index = SourceIndex.build(src)
    comments, warnings = collect_token_comments(src, index)
    assert not warnings
    clusters = _build_clusters(comments)
    cml = [c for c in clusters if c.is_cml]
    assert len(cml) == 2
    assert cml[0].record_type == "gb"
    assert cml[1].record_type == "ge"
    plains = [c for c in clusters if (not c.is_cml) and c.parts[0].full_line]
    assert any("# inner" in c.parts[0].text for c in plains)
    assert any("# outer" in c.parts[0].text for c in plains)
    for c in plains:
        texts = [p.text for p in c.parts]
        assert not ("# inner" in "".join(texts) and "# outer" in "".join(texts))

    cf = getControlFlowFromMemory(src)
    # Both CML records should be recoverable (module leading and/or on first stmt)
    recovered = list(cf.leadingCMLComments)
    for frag in cf.nsuite:
        recovered.extend(getattr(frag, "leadingCMLComments", []) or [])
    types = {c.recordType for c in recovered}
    assert {"gb", "ge"} <= types


def test_case_keyword_ignores_comment_and_body_name():
    """B06: case span from token stream, not rfind over comments/body names."""
    src = (
        "def classify(x):\n"
        "    match x:\n"
        "        # decoy word case in comment\n"
        "        case 0:\n"
        "            case = 1\n"
        "            return case\n"
        "        case (\n"
        "            a,\n"
        "            b,\n"
        "        ):\n"
        "            return a\n"
    )
    cf = getControlFlowFromMemory(src)
    fn = cf.nsuite[0]
    match = next(x for x in fn.nsuite if x.kind == 25)
    assert len(match.parts) == 2
    first, second = match.parts
    fb, _ = first.getAbsPosRange()
    sb, _ = second.getAbsPosRange()
    assert src[fb : fb + 4] == "case"
    assert src[sb : sb + 5] == "case "
    assert "# decoy" not in src[fb : fb + 20]


def test_multiline_def_header_side_comment():
    """D06: side comment on closing header line attaches to the function."""
    src = "def calculate(\n    value,\n):  # comment\n    return value\n"
    cf = getControlFlowFromMemory(src)
    fn = cf.nsuite[0]
    assert fn.kind == 7
    assert fn.sideComment is not None
    assert "# comment" in fn.sideComment.getDisplayValue()
    assert not any("unattached side comment" in (w[2] if isinstance(w, tuple) else str(w)) for w in (cf.warnings or []))
