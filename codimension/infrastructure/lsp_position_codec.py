# -*- coding: utf-8 -*-
#
# codimension - LSP position encoding boundary (R201)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""LspPositionCodec: per-process LSP encoding ↔ Unicode offsets (R201).

Codimension internals use Unicode character offsets exclusively
(:class:`~core.document_snapshot.DocumentSnapshot`,
:class:`~core.symbol_index.SourceSpan`). This module is the **only** place
that converts to/from LSP ``Position`` / ``Range`` using a fixed encoding
negotiated for one language-server process (UTF-16 by default; UTF-8 / UTF-32
when negotiated).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.document_snapshot import DocumentSnapshot
from core.symbol_index import SourceSpan


class LspPositionEncoding(str, Enum):
    """LSP ``PositionEncodingKind`` values (spec 3.17+)."""

    UTF8 = "utf-8"
    UTF16 = "utf-16"
    UTF32 = "utf-32"


@dataclass(frozen=True, slots=True)
class LspPosition:
    """LSP Position: 0-based ``line`` and encoding-unit ``character``."""

    line: int
    character: int

    def __post_init__(self) -> None:
        """Reject negative coordinates."""
        if self.line < 0:
            raise ValueError(f"line must be >= 0, got {self.line}")
        if self.character < 0:
            raise ValueError(f"character must be >= 0, got {self.character}")

    def to_dict(self) -> dict[str, int]:
        """Return JSON-shaped LSP Position object."""
        return {"line": self.line, "character": self.character}

    @classmethod
    def from_dict(cls, data: dict[str, int]) -> LspPosition:
        """Build from an LSP Position mapping."""
        return cls(line=int(data["line"]), character=int(data["character"]))


@dataclass(frozen=True, slots=True)
class LspRange:
    """LSP Range: half-open ``[start, end)`` in LSP coordinates."""

    start: LspPosition
    end: LspPosition

    def to_dict(self) -> dict[str, dict[str, int]]:
        """Return JSON-shaped LSP Range object."""
        return {"start": self.start.to_dict(), "end": self.end.to_dict()}

    @classmethod
    def from_dict(cls, data: dict[str, dict[str, int]]) -> LspRange:
        """Build from an LSP Range mapping."""
        return cls(
            start=LspPosition.from_dict(data["start"]),
            end=LspPosition.from_dict(data["end"]),
        )


def _utf16_units(ch: str) -> int:
    """Return UTF-16 code-unit count for one Unicode scalar (1 or 2)."""
    return 2 if ord(ch) > 0xFFFF else 1


def _line_encoding_length(line: str, encoding: LspPositionEncoding) -> int:
    """Return encoded length of ``line`` (no newline) in ``encoding`` units."""
    if encoding is LspPositionEncoding.UTF32:
        return len(line)
    if encoding is LspPositionEncoding.UTF16:
        return sum(_utf16_units(ch) for ch in line)
    # utf-8
    return len(line.encode("utf-8"))


def _char_index_to_encoded(line: str, char_index: int, encoding: LspPositionEncoding) -> int:
    """Convert 0-based Unicode column → encoded character offset on ``line``."""
    if char_index <= 0:
        return 0
    clipped = min(char_index, len(line))
    prefix = line[:clipped]
    if encoding is LspPositionEncoding.UTF32:
        return len(prefix)
    if encoding is LspPositionEncoding.UTF16:
        return sum(_utf16_units(ch) for ch in prefix)
    return len(prefix.encode("utf-8"))


def _encoded_to_char_index(line: str, encoded: int, encoding: LspPositionEncoding) -> int:
    """Convert encoded character offset → 0-based Unicode column on ``line``.

    Mid-code-unit / mid-codepoint targets clamp to the nearest preceding
    complete character boundary (LSP clients may send past EOL; we clamp).
    """
    if encoded <= 0:
        return 0
    if encoding is LspPositionEncoding.UTF32:
        return min(encoded, len(line))

    if encoding is LspPositionEncoding.UTF16:
        units = 0
        for idx, ch in enumerate(line):
            next_units = units + _utf16_units(ch)
            if next_units > encoded:
                return idx
            units = next_units
            if units == encoded:
                return idx + 1
        return len(line)

    # utf-8: walk code points so we never decode a truncated prefix
    byte_pos = 0
    for idx, ch in enumerate(line):
        ch_bytes = len(ch.encode("utf-8"))
        next_pos = byte_pos + ch_bytes
        if next_pos > encoded:
            return idx
        byte_pos = next_pos
        if byte_pos == encoded:
            return idx + 1
    return len(line)


class LspPositionCodec:
    """Bidirectional Unicode ↔ LSP position converter for one server process.

    Construct once after initialize / capability negotiation and reuse for
    that ``(language_id, workspace_root, toolchain)`` process.
    """

    def __init__(self, encoding: LspPositionEncoding = LspPositionEncoding.UTF16) -> None:
        if not isinstance(encoding, LspPositionEncoding):
            raise TypeError(f"encoding must be LspPositionEncoding, got {type(encoding)!r}")
        self._encoding = encoding

    @property
    def encoding(self) -> LspPositionEncoding:
        """Position encoding fixed for this codec instance."""
        return self._encoding

    def to_lsp_position(self, document: DocumentSnapshot, offset: int) -> LspPosition:
        """Map absolute Unicode ``offset`` → LSP Position."""
        line, col = document.offset_to_line_col(offset)
        character = _char_index_to_encoded(document.line_text(line), col, self._encoding)
        return LspPosition(line=line, character=character)

    def to_internal_offset(self, document: DocumentSnapshot, position: LspPosition) -> int:
        """Map LSP Position → absolute Unicode offset."""
        line = min(position.line, max(document.line_count - 1, 0))
        col = _encoded_to_char_index(document.line_text(line), position.character, self._encoding)
        # ``core.*`` imports resolve separately from ``codimension.core.*`` under mypy;
        # coerce so ``warn_return_any`` stays clean (same pattern as other headless layers).
        return int(document.line_col_to_offset(line, col))

    def to_lsp_range(self, document: DocumentSnapshot, span: SourceSpan) -> LspRange:
        """Map internal :class:`SourceSpan` → LSP Range."""
        return LspRange(
            start=self.to_lsp_position(document, span.start),
            end=self.to_lsp_position(document, span.end),
        )

    def to_internal_span(self, document: DocumentSnapshot, lsp_range: LspRange) -> SourceSpan:
        """Map LSP Range → internal half-open :class:`SourceSpan`."""
        start = self.to_internal_offset(document, lsp_range.start)
        end = self.to_internal_offset(document, lsp_range.end)
        if end < start:
            end = start
        return SourceSpan(start=start, end=end)


__all__ = [
    "LspPosition",
    "LspPositionCodec",
    "LspPositionEncoding",
    "LspRange",
]
