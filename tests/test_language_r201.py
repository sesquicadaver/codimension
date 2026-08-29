# -*- coding: utf-8 -*-
"""R201: DocumentSnapshot versioned edits + LspPositionCodec encodings."""

from __future__ import annotations

import pytest
from core.document_snapshot import (
    DocumentSnapshot,
    StaleDocumentEditError,
    TextEdit,
    VersionedSpan,
)
from core.symbol_index import SourceSpan
from infrastructure.lsp_position_codec import (
    LspPosition,
    LspPositionCodec,
    LspPositionEncoding,
    LspRange,
)


def test_document_snapshot_line_col_roundtrip() -> None:
    doc = DocumentSnapshot(uri="file:///a.py", text="ab\ncde\n")
    assert doc.line_count == 3  # trailing newline → empty line 2
    assert doc.offset_to_line_col(0) == (0, 0)
    assert doc.offset_to_line_col(3) == (1, 0)
    assert doc.line_col_to_offset(1, 2) == 5
    assert doc.slice(SourceSpan(0, 2)) == "ab"


def test_stale_edits_rejected() -> None:
    doc = DocumentSnapshot(uri="mem:x", text="hello", version=3)
    with pytest.raises(StaleDocumentEditError) as exc:
        doc.apply_edits(2, [TextEdit(SourceSpan(0, 1), "H")])
    assert exc.value.expected == 2
    assert exc.value.actual == 3


def test_apply_edits_bumps_version_and_text() -> None:
    doc = DocumentSnapshot(uri="mem:x", text="abcdef", version=0)
    next_doc = doc.apply_edits(
        0,
        [
            TextEdit(SourceSpan(1, 3), "XY"),  # bc → XY
            TextEdit(SourceSpan(4, 5), "Z"),  # e → Z
        ],
    )
    assert next_doc.version == 1
    assert next_doc.text == "aXYdZf"
    assert doc.text == "abcdef"  # immutable


def test_overlapping_edits_rejected() -> None:
    doc = DocumentSnapshot(uri="mem:x", text="abcd")
    with pytest.raises(ValueError, match="overlapping"):
        doc.apply_edits(
            0,
            [
                TextEdit(SourceSpan(0, 2), "A"),
                TextEdit(SourceSpan(1, 3), "B"),
            ],
        )


def test_versioned_span_and_accepts_version() -> None:
    doc = DocumentSnapshot(uri="mem:x", text="a", version=7)
    vs = VersionedSpan(version=7, span=SourceSpan(0, 1))
    assert doc.accepts_version(vs.version)
    assert not doc.accepts_version(6)
    with pytest.raises(StaleDocumentEditError):
        doc.ensure_version(6)


def test_codec_utf16_astral_plane() -> None:
    # 😀 is U+1F600 → two UTF-16 code units
    text = "a😀b"
    doc = DocumentSnapshot(uri="mem:emoji", text=text)
    codec = LspPositionCodec(LspPositionEncoding.UTF16)
    # offset of 'b' is Unicode index 2
    pos = codec.to_lsp_position(doc, 2)
    assert pos == LspPosition(0, 3)  # a=1 + emoji=2
    assert codec.to_internal_offset(doc, pos) == 2
    span = codec.to_internal_span(doc, LspRange(LspPosition(0, 1), LspPosition(0, 3)))
    assert doc.slice(span) == "😀"


def test_codec_utf8_multibyte() -> None:
    text = "café"  # é is 2 UTF-8 bytes
    doc = DocumentSnapshot(uri="mem:cafe", text=text)
    codec = LspPositionCodec(LspPositionEncoding.UTF8)
    # Unicode offset of final 'é' is 3
    pos = codec.to_lsp_position(doc, 3)
    assert pos.character == len("caf".encode("utf-8"))  # 3
    assert codec.to_internal_offset(doc, pos) == 3
    end = codec.to_lsp_position(doc, 4)
    assert end.character == len(text.encode("utf-8"))


def test_codec_utf32_matches_unicode_columns() -> None:
    text = "a😀b"
    doc = DocumentSnapshot(uri="mem:u32", text=text)
    codec = LspPositionCodec(LspPositionEncoding.UTF32)
    assert codec.to_lsp_position(doc, 2) == LspPosition(0, 2)
    assert codec.to_internal_offset(doc, LspPosition(0, 2)) == 2


def test_codec_roundtrip_multiline() -> None:
    doc = DocumentSnapshot(uri="mem:m", text="one\ntwo\n")
    codec = LspPositionCodec(LspPositionEncoding.UTF16)
    for offset in range(len(doc.text) + 1):
        pos = codec.to_lsp_position(doc, offset)
        assert codec.to_internal_offset(doc, pos) == offset


def test_empty_apply_still_bumps_version() -> None:
    doc = DocumentSnapshot(uri="mem:e", text="x", version=1)
    nxt = doc.apply_edits(1, [])
    assert nxt.version == 2
    assert nxt.text == "x"
