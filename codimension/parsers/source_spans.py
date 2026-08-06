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
import io
import tokenize
from dataclasses import dataclass
from typing import Literal


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

    def line_col_from_abs(self, abs_pos: int) -> tuple[int, int]:
        """Return ``(lineno, 1-based char column)`` for an absolute character offset."""
        abs_pos = max(0, min(abs_pos, len(self.source)))
        starts = self._line_starts
        # Last start with start <= abs_pos
        lo, hi = 0, len(starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if starts[mid] <= abs_pos:
                lo = mid
            else:
                hi = mid - 1
        lineno = lo + 1
        col = abs_pos - starts[lo] + 1
        return lineno, col

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
        """Absolute 0-based character index for AST line + UTF-8 byte column.

        Prefer the explicit alias :meth:`abs_from_utf8_byte_column` at call sites
        that convert Python ``ast`` offsets.
        """
        return self.abs_from_utf8_byte_column(lineno, byte_col)

    def abs_from_utf8_byte_column(self, lineno: int, byte_col: int) -> int:
        """Absolute 0-based character index from a UTF-8 byte column (AST)."""
        return self.line_start(lineno) + self.byte_col_to_char_col(lineno, byte_col)

    def abs_from_character_column(self, lineno: int, char_col: int) -> int:
        """Absolute 0-based character index from a character column (tokenize).

        ``tokenize`` reports columns in Unicode code-point / ``str`` indices, not
        UTF-8 bytes. Do not pass these through :meth:`abs_from_utf8_byte_column`.
        """
        if char_col <= 0:
            return self.line_start(lineno)
        line = self.line_text(lineno)
        return self.line_start(lineno) + min(char_col, len(line))

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


@dataclass(frozen=True, slots=True)
class TokenIndex:
    """Precomputed ``tokenize`` stream for one decoded source string (B04).

    Used to resolve definition keyword / identifier / header-colon positions
    that the AST does not expose separately.
    """

    tokens: tuple[tokenize.TokenInfo, ...]

    @classmethod
    def build(cls, source: str) -> TokenIndex:
        """Tokenize ``source`` once; tolerate incomplete buffers via empty index."""
        tokens: list[tokenize.TokenInfo] = []
        try:
            tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
        except (tokenize.TokenError, IndentationError):
            tokens = []
        return cls(tokens=tuple(tokens))

    def tok_abs(self, index: SourceIndex, tok: tokenize.TokenInfo) -> int:
        """Absolute character offset of a tokenize token start."""
        return index.abs_from_character_column(tok.start[0], tok.start[1])

    def suite_header_positions(
        self,
        index: SourceIndex,
        node: ast.AST,
        name: str,
        kind: Literal["class", "def", "async"],
    ) -> tuple[int, int, int, int, int, int, int] | None:
        """Return name and keyword/colon positions for a class/def header.

        Returns
        -------
        (name_ln, name_pos, name_abs, kw_ln, kw_pos, colon_ln, colon_pos)
            All line/pos values are 1-based UI columns; ``name_abs`` is 0-based.
            ``None`` if the token stream cannot resolve the header.
        """
        if not self.tokens:
            return None

        start_ln = getattr(node, "lineno", 1) or 1
        start_col = getattr(node, "col_offset", 0) or 0
        start_abs = index.abs_from_utf8_byte_column(start_ln, start_col)
        body = getattr(node, "body", None) or []
        if body:
            first = body[0]
            body_begin = index.abs_from_utf8_byte_column(
                getattr(first, "lineno", start_ln) or start_ln,
                getattr(first, "col_offset", 0) or 0,
            )
        else:
            body_begin = index.node_span(node)[1]

        i = 0
        n = len(self.tokens)
        while i < n and self.tok_abs(index, self.tokens[i]) < start_abs:
            i += 1

        kw_tok: tokenize.TokenInfo | None = None
        if kind == "async":
            while i < n:
                tok = self.tokens[i]
                i += 1
                if tok.type == tokenize.NAME and tok.string == "async":
                    kw_tok = tok
                    break
            while i < n:
                tok = self.tokens[i]
                i += 1
                if tok.type == tokenize.NAME and tok.string == "def":
                    break
        elif kind == "def":
            while i < n:
                tok = self.tokens[i]
                i += 1
                if tok.type == tokenize.NAME and tok.string == "def":
                    kw_tok = tok
                    break
        else:  # class
            while i < n:
                tok = self.tokens[i]
                i += 1
                if tok.type == tokenize.NAME and tok.string == "class":
                    kw_tok = tok
                    break

        if kw_tok is None:
            return None

        name_tok: tokenize.TokenInfo | None = None
        while i < n:
            tok = self.tokens[i]
            abs_t = self.tok_abs(index, tok)
            if abs_t >= body_begin:
                break
            if tok.type == tokenize.NAME and tok.string == name:
                name_tok = tok
                break
            i += 1
        if name_tok is None:
            return None

        colon_tok: tokenize.TokenInfo | None = None
        j = i + 1
        while j < n:
            tok = self.tokens[j]
            abs_t = self.tok_abs(index, tok)
            if abs_t >= body_begin:
                break
            if tok.type == tokenize.OP and tok.string == ":":
                colon_tok = tok
            j += 1
        if colon_tok is None:
            return None

        name_abs = self.tok_abs(index, name_tok)
        name_ln, name_pos = index.line_col_from_abs(name_abs)
        kw_abs = self.tok_abs(index, kw_tok)
        kw_ln, kw_pos = index.line_col_from_abs(kw_abs)
        colon_abs = self.tok_abs(index, colon_tok)
        colon_ln, colon_pos = index.line_col_from_abs(colon_abs)
        return name_ln, name_pos, name_abs, kw_ln, kw_pos, colon_ln, colon_pos

    def find_name_before(
        self,
        index: SourceIndex,
        name: str,
        *,
        lo_abs: int,
        hi_abs: int,
        column: int | None = None,
    ) -> tuple[int, int, int] | None:
        """Return ``(abs, lineno, 1-based col)`` for the last NAME ``name`` in range.

        ``column``, when set, is the 0-based character column that the token must
        start at (used to ignore deeper soft-keyword lookalikes such as
        ``case = 1`` inside a prior match arm — B06).
        """
        best: tokenize.TokenInfo | None = None
        for tok in self.tokens:
            if tok.type != tokenize.NAME or tok.string != name:
                continue
            if column is not None and tok.start[1] != column:
                continue
            abs_t = self.tok_abs(index, tok)
            if lo_abs <= abs_t < hi_abs:
                best = tok
        if best is None:
            return None
        abs_t = self.tok_abs(index, best)
        ln, pos = index.line_col_from_abs(abs_t)
        return abs_t, ln, pos


def build_source_index(source: str) -> SourceIndex:
    """Public factory for :class:`SourceIndex`."""
    return SourceIndex.build(source)


def build_token_index(source: str) -> TokenIndex:
    """Public factory for :class:`TokenIndex`."""
    return TokenIndex.build(source)


def node_source_segment(source: str, node: ast.AST) -> str | None:
    """Prefer ``ast.get_source_segment``; fall back to indexed span slice."""
    segment = ast.get_source_segment(source, node)
    if segment is not None:
        return segment
    index = SourceIndex.build(source)
    begin, end, *_ = index.node_span(node)
    return index.slice(begin, end)
