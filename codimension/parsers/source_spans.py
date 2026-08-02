# -*- coding: utf-8 -*-
#
# codimension - shared source span helpers for brief_ast / flow_ast
# Copyright (C) 2026  Codimension fork contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Byte/character source span utilities for pure-Python parsers.

Implements the span rules from ``doc/technology/parser-contract.md``:
precomputed line starts, UTF-8 byte offset → character index, exclusive end.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceIndex:
    """Precomputed line table for one decoded source string."""

    source: str
    # Character offset of the first character of each 1-based line.
    _line_starts: tuple[int, ...]

    @classmethod
    def build(cls, source: str) -> SourceIndex:
        """Build line-start table in O(len(source))."""
        starts: list[int] = [0]
        for idx, ch in enumerate(source):
            if ch == "\n":
                starts.append(idx + 1)
        return cls(source=source, _line_starts=tuple(starts))

    @property
    def line_count(self) -> int:
        """Number of lines (last line may be empty after trailing newline)."""
        if not self.source:
            return 1
        # If source ends with \\n, line_starts already has the next empty line start.
        return len(self._line_starts)

    def line_start(self, lineno: int) -> int:
        """Return 0-based character offset of the start of ``lineno`` (1-based)."""
        if lineno < 1:
            return 0
        starts = self._line_starts
        if lineno > len(starts):
            return len(self.source)
        return starts[lineno - 1]

    def line_text(self, lineno: int) -> str:
        """Return the text of ``lineno`` without the terminating newline."""
        start = self.line_start(lineno)
        if lineno < len(self._line_starts):
            end = self._line_starts[lineno] - 1  # exclude '\\n'
            return self.source[start:end]
        return self.source[start:]

    def byte_col_to_char_col(self, lineno: int, byte_col: int) -> int:
        """Convert a UTF-8 byte column on ``lineno`` to a 0-based character column."""
        if byte_col <= 0:
            return 0
        line = self.line_text(lineno)
        encoded = line.encode("utf-8")
        if byte_col >= len(encoded):
            return len(line)
        # Decode only the prefix of ``byte_col`` bytes; may land mid-codepoint —
        # use 'replace' solely for pathological truncated offsets.
        return len(encoded[:byte_col].decode("utf-8", errors="replace"))

    def abs_char_pos(self, lineno: int, byte_col: int) -> int:
        """Absolute 0-based character index for AST line + UTF-8 byte column."""
        return self.line_start(lineno) + self.byte_col_to_char_col(lineno, byte_col)

    def node_span(self, node: ast.AST) -> tuple[int, int, int, int, int, int]:
        """Return (begin, end, beginLine, endLine, beginPos, endPos).

        ``begin``/``end`` are 0-based exclusive-end character offsets.
        ``beginPos``/``endPos`` are 1-based character columns for UI.
        """
        ln = getattr(node, "lineno", 1) or 1
        co = getattr(node, "col_offset", 0) or 0
        eln = getattr(node, "end_lineno", ln) or ln
        eco = getattr(node, "end_col_offset", co) or co

        begin = self.abs_char_pos(ln, co)
        end = self.abs_char_pos(eln, eco)
        if end < begin:
            end = begin

        begin_pos = self.byte_col_to_char_col(ln, co) + 1
        end_pos = self.byte_col_to_char_col(eln, eco) + 1
        return begin, end, ln, eln, begin_pos, end_pos

    def slice(self, begin: int, end: int) -> str:
        """Return ``source[begin:end]`` with bounds clamping."""
        begin = max(0, begin)
        end = max(begin, min(end, len(self.source)))
        return self.source[begin:end]


def build_source_index(source: str) -> SourceIndex:
    """Public factory for :class:`SourceIndex`."""
    return SourceIndex.build(source)


def node_source_segment(source: str, node: ast.AST) -> str | None:
    """Prefer ``ast.get_source_segment``; fall back to indexed span slice."""
    segment = ast.get_source_segment(source, node)
    if segment is not None:
        return segment
    index = SourceIndex.build(source)
    begin, end, *_ = index.node_span(node)
    return index.slice(begin, end)
