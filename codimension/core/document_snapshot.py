# -*- coding: utf-8 -*-
#
# codimension - versioned document buffer for polyglot layer (R201)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""DocumentSnapshot: Unicode offsets + versioned edits (R201).

Internal coordinates are **Unicode character** indices only (same convention as
:class:`~core.symbol_index.SourceSpan`). LSP UTF-8 / UTF-16 encodings stay in
:mod:`infrastructure.lsp_position_codec` and must not leak into ``core``.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Sequence

from .symbol_index import SourceSpan


class StaleDocumentEditError(ValueError):
    """Raised when an edit targets a document version that is no longer current."""

    def __init__(self, *, expected: int, actual: int, uri: str) -> None:
        self.expected = expected
        self.actual = actual
        self.uri = uri
        super().__init__(
            f"stale document edit for {uri!r}: expected version {expected}, "
            f"document is at {actual}"
        )


@dataclass(frozen=True, slots=True)
class TextEdit:
    """Half-open Unicode span replacement (internal coordinates only)."""

    span: SourceSpan
    new_text: str

    def __post_init__(self) -> None:
        """Reject non-SourceSpan ranges."""
        if not isinstance(self.span, SourceSpan):
            raise TypeError(f"span must be SourceSpan, got {type(self.span)!r}")


@dataclass(frozen=True, slots=True)
class VersionedSpan:
    """Diagnostic / result range bound to a document version."""

    version: int
    span: SourceSpan

    def __post_init__(self) -> None:
        """Reject negative versions and non-spans."""
        if self.version < 0:
            raise ValueError(f"version must be >= 0, got {self.version}")
        if not isinstance(self.span, SourceSpan):
            raise TypeError(f"span must be SourceSpan, got {type(self.span)!r}")


@dataclass(frozen=True, slots=True)
class DocumentSnapshot:
    """Immutable text buffer with monotonic version for LSP / editor sync.

    Attributes:
        uri: Document identity (file URI or project-relative path string).
        text: Full decoded Unicode source.
        version: Monotonic document version (starts at 0 unless set).
        language_id: Optional language id (e.g. ``python``, ``rust``).
    """

    uri: str
    text: str
    version: int = 0
    language_id: str = ""
    _line_starts: tuple[int, ...] = field(
        init=False, repr=False, compare=False, hash=False
    )

    def __post_init__(self) -> None:
        """Validate identity and version; build private line-start table."""
        if not self.uri:
            raise ValueError("uri must be non-empty")
        if self.version < 0:
            raise ValueError(f"version must be >= 0, got {self.version}")
        starts: list[int] = [0]
        for idx, ch in enumerate(self.text):
            if ch == "\n":
                starts.append(idx + 1)
        object.__setattr__(self, "_line_starts", tuple(starts))

    @property
    def line_count(self) -> int:
        """Number of lines (trailing newline yields an extra empty line)."""
        if not self.text:
            return 1
        return len(self._line_starts)

    def line_start(self, line: int) -> int:
        """Return 0-based Unicode offset of the start of ``line`` (0-based)."""
        starts = self._line_starts
        if line < 0:
            return 0
        if line >= len(starts):
            return len(self.text)
        return starts[line]

    def line_text(self, line: int) -> str:
        """Return ``line`` text without a terminating ``\\n`` (0-based line)."""
        starts = self._line_starts
        start = self.line_start(line)
        if line + 1 < len(starts):
            return self.text[start : starts[line + 1] - 1]
        return self.text[start:]

    def offset_to_line_col(self, offset: int) -> tuple[int, int]:
        """Map absolute Unicode offset → ``(line, col)`` (both 0-based)."""
        offset = max(0, min(offset, len(self.text)))
        starts = self._line_starts
        lo, hi = 0, len(starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if starts[mid] <= offset:
                lo = mid
            else:
                hi = mid - 1
        return lo, offset - starts[lo]

    def line_col_to_offset(self, line: int, col: int) -> int:
        """Map 0-based ``(line, Unicode col)`` → absolute Unicode offset."""
        line_body = self.line_text(line)
        start = self.line_start(line)
        if col <= 0:
            return start
        return start + min(col, len(line_body))

    def slice(self, span: SourceSpan) -> str:
        """Return ``text[span.start:span.end]`` with clamping."""
        begin = max(0, span.start)
        end = max(begin, min(span.end, len(self.text)))
        return self.text[begin:end]

    def accepts_version(self, version: int) -> bool:
        """Return True when ``version`` matches this snapshot."""
        return version == self.version

    def ensure_version(self, version: int) -> None:
        """Raise :class:`StaleDocumentEditError` when ``version`` is stale."""
        if version != self.version:
            raise StaleDocumentEditError(
                expected=version, actual=self.version, uri=self.uri
            )

    def with_text(self, text: str, *, bump_version: bool = True) -> DocumentSnapshot:
        """Return a new snapshot with ``text`` (optionally bump version by 1)."""
        new_version = self.version + 1 if bump_version else self.version
        return DocumentSnapshot(
            uri=self.uri,
            text=text,
            version=new_version,
            language_id=self.language_id,
        )

    def apply_edits(
        self,
        expected_version: int,
        edits: Sequence[TextEdit],
    ) -> DocumentSnapshot:
        """Apply non-overlapping Unicode edits when ``expected_version`` matches.

        Edits are applied from highest ``span.start`` to lowest so earlier
        offsets stay valid. Overlapping spans raise ``ValueError``.
        On success the returned snapshot has ``version == self.version + 1``.
        """
        self.ensure_version(expected_version)
        if not edits:
            return replace(self, version=self.version + 1)

        ascending = sorted(edits, key=lambda e: (e.span.start, e.span.end))
        prev_end = 0
        length = len(self.text)
        for edit in ascending:
            if edit.span.start > length or edit.span.end > length:
                raise ValueError(
                    f"edit span {edit.span!r} out of range for document length {length}"
                )
            if edit.span.start < prev_end:
                raise ValueError(
                    f"overlapping edits: span {edit.span!r} overlaps previous end {prev_end}"
                )
            prev_end = edit.span.end

        text = self.text
        for edit in reversed(ascending):
            text = text[: edit.span.start] + edit.new_text + text[edit.span.end :]
        return DocumentSnapshot(
            uri=self.uri,
            text=text,
            version=self.version + 1,
            language_id=self.language_id,
        )


__all__ = [
    "DocumentSnapshot",
    "StaleDocumentEditError",
    "TextEdit",
    "VersionedSpan",
]
