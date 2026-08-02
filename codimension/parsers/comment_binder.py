# -*- coding: utf-8 -*-
#
# codimension - tokenize-based comment / CML attachment for flow_ast
# Copyright (C) 2026
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Recover comments, CML, shebang and encoding lines and attach them to fragments."""

from __future__ import annotations

import io
import re
import tokenize
from dataclasses import dataclass, field
from typing import Any

from .source_spans import SourceIndex

COMMENT_FRAGMENT = 3
CML_COMMENT_FRAGMENT = 63

_CML_HEAD = re.compile(r"^#\s*cml\s+(\d+)\s+(\S+)(.*)$")
_CML_CONT = re.compile(r"^#\s*cml\+\s*(.*)$")
_ENCODING_COOKIE = re.compile(r"^[ \t\f]*#.*?coding[:=][ \t]*([-_.a-zA-Z0-9]+)")
_PROP_PAIR = re.compile(r'(\w+)\s*=\s*("(?:\\.|[^"])*"|\'(?:\\.|[^\'])*\'|\S+)')


@dataclass
class _TokComment:
    """One COMMENT token with absolute character positions."""

    begin: int
    end: int
    begin_line: int
    end_line: int
    begin_pos: int
    end_pos: int
    text: str
    full_line: bool
    line_content: str


@dataclass
class _CommentCluster:
    """Adjacent full-line comments or a single side comment."""

    parts: list[_TokComment] = field(default_factory=list)
    is_cml: bool = False
    version: int = 0
    record_type: str = ""
    properties: dict[str, str] = field(default_factory=dict)
    consumed: bool = False

    @property
    def begin_line(self) -> int:
        return self.parts[0].begin_line

    @property
    def end_line(self) -> int:
        return self.parts[-1].end_line

    @property
    def begin(self) -> int:
        return self.parts[0].begin

    @property
    def end(self) -> int:
        return self.parts[-1].end


class _CommentPart:
    """Single comment line part (C-parser compatible)."""

    def __init__(
        self,
        begin: int,
        end: int,
        begin_line: int,
        end_line: int,
        begin_pos: int,
        end_pos: int,
        content: str,
        line_content: str,
    ) -> None:
        self.begin = begin
        self.end = end
        self.beginLine = begin_line
        self.endLine = end_line
        self.beginPos = begin_pos
        self.endPos = end_pos
        self._content = content
        self._line_content = line_content

    def getContent(self) -> str:
        return self._content

    def getLineContent(self) -> str:
        return self._line_content


class _AttachedComment:
    """leadingComment / sideComment object expected by Flow UI."""

    def __init__(self, cluster: _CommentCluster) -> None:
        self.kind = COMMENT_FRAGMENT
        self.parts = [
            _CommentPart(
                p.begin,
                p.end,
                p.begin_line,
                p.end_line,
                p.begin_pos,
                p.end_pos,
                p.text,
                p.line_content,
            )
            for p in cluster.parts
        ]
        first, last = self.parts[0], self.parts[-1]
        self.begin = first.begin
        self.end = last.end
        self.beginLine = first.beginLine
        self.endLine = last.endLine
        self.beginPos = first.beginPos
        self.endPos = last.endPos

    def getDisplayValue(self) -> str:
        return "\n".join(p.getContent() for p in self.parts)

    def getLineRange(self) -> tuple[int, int]:
        return (self.beginLine, self.endLine)

    def getAbsPosRange(self) -> tuple[int, int]:
        return (self.begin, self.end)

    def extend_with(self, other: _AttachedComment) -> None:
        """Merge another attached comment into this one."""
        self.parts.extend(other.parts)
        self.end = other.end
        self.endLine = other.endLine
        self.endPos = other.endPos


class _CMLRawComment:
    """Raw CML comment fragment (replaced later by CMLVersion.validate*)."""

    def __init__(self, cluster: _CommentCluster) -> None:
        self.kind = CML_COMMENT_FRAGMENT
        self.version = cluster.version
        self.recordType = cluster.record_type
        self.properties = dict(cluster.properties)
        self.parts = [
            _CommentPart(
                p.begin,
                p.end,
                p.begin_line,
                p.end_line,
                p.begin_pos,
                p.end_pos,
                p.text,
                p.line_content,
            )
            for p in cluster.parts
        ]
        first, last = self.parts[0], self.parts[-1]
        self.begin = first.begin
        self.end = last.end
        self.beginLine = first.beginLine
        self.endLine = last.endLine
        self.beginPos = first.beginPos
        self.endPos = last.endPos
        self.leadingComment = None
        self.sideComment = None
        self.leadingCMLComments: list[Any] = []
        self.sideCMLComments: list[Any] = []

    def getDisplayValue(self) -> str:
        return "\n".join(p.getContent() for p in self.parts)

    def getLineRange(self) -> tuple[int, int]:
        return (self.beginLine, self.endLine)

    def getAbsPosRange(self) -> tuple[int, int]:
        return (self.begin, self.end)


class _IndependentCommentFrag:
    """COMMENT_FRAGMENT node inserted into a suite (independent comment)."""

    def __init__(self, cluster: _CommentCluster) -> None:
        self.kind = COMMENT_FRAGMENT
        attached = _AttachedComment(cluster)
        self.parts = attached.parts
        self.begin = attached.begin
        self.end = attached.end
        self.beginLine = attached.beginLine
        self.endLine = attached.endLine
        self.beginPos = attached.beginPos
        self.endPos = attached.endPos
        self.body = type(
            "Body",
            (),
            {
                "begin": self.begin,
                "end": self.end,
                "beginLine": self.beginLine,
                "endLine": self.endLine,
                "beginPos": self.beginPos,
                "endPos": self.endPos,
                "getLineRange": lambda s=None: (self.beginLine, self.endLine),
                "getAbsPosRange": lambda s=None: (self.begin, self.end),
            },
        )()
        self.leadingComment = None
        self.sideComment = None
        self.leadingCMLComments: list[Any] = []
        self.sideCMLComments: list[Any] = []
        self.nsuite: list[Any] = []

    def getDisplayValue(self) -> str:
        return "\n".join(p.getContent() for p in self.parts)

    def getLineRange(self) -> tuple[int, int]:
        return (self.beginLine, self.endLine)

    def getAbsPosRange(self) -> tuple[int, int]:
        return (self.begin, self.end)


def _parse_properties(tail: str) -> dict[str, str]:
    props: dict[str, str] = {}
    for match in _PROP_PAIR.finditer(tail or ""):
        key = match.group(1)
        raw = match.group(2)
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
            props[key] = raw[1:-1]
        else:
            props[key] = raw
    return props


def _annotate_cml(cluster: _CommentCluster) -> None:
    head = _CML_HEAD.match(cluster.parts[0].text.strip())
    if not head:
        return
    cluster.is_cml = True
    cluster.version = int(head.group(1))
    cluster.record_type = head.group(2)
    cluster.properties = _parse_properties(head.group(3))
    for cont in cluster.parts[1:]:
        m = _CML_CONT.match(cont.text.strip())
        if not m:
            break
        cluster.properties.update(_parse_properties(m.group(1)))


def collect_token_comments(source: str, index: SourceIndex) -> tuple[list[_TokComment], list[str]]:
    """Collect COMMENT tokens with UTF-8-aware absolute positions.

    Returns ``(comments, warnings)``. Tokenization failures do not raise; a
    warning string is returned so callers can surface them on the control flow.
    """
    lines = source.splitlines(keepends=True)
    result: list[_TokComment] = []
    warnings: list[str] = []
    readline = io.StringIO(source).readline
    try:
        for tok in tokenize.generate_tokens(readline):
            if tok.type != tokenize.COMMENT:
                continue
            start_ln, start_col = tok.start
            end_ln, end_col = tok.end
            begin = index.abs_char_pos(start_ln, start_col)
            end = index.abs_char_pos(end_ln, end_col)
            line_src = lines[start_ln - 1] if 0 < start_ln <= len(lines) else ""
            before = line_src[:start_col]
            full_line = before.strip() == ""
            result.append(
                _TokComment(
                    begin=begin,
                    end=end,
                    begin_line=start_ln,
                    end_line=end_ln,
                    begin_pos=start_col + 1,
                    end_pos=end_col + 1,
                    text=tok.string,
                    full_line=full_line,
                    line_content=line_src.rstrip("\r\n"),
                )
            )
    except tokenize.TokenError as exc:
        warnings.append(f"tokenize error while collecting comments: {exc}")
    return result, warnings


def _build_clusters(comments: list[_TokComment]) -> list[_CommentCluster]:
    """Group consecutive full-line comments; each side comment is its own cluster."""
    clusters: list[_CommentCluster] = []
    i = 0
    n = len(comments)
    while i < n:
        c = comments[i]
        if not c.full_line:
            cluster = _CommentCluster(parts=[c])
            _annotate_cml(cluster)
            clusters.append(cluster)
            i += 1
            continue

        group = [c]
        j = i + 1
        while j < n:
            nxt = comments[j]
            if not nxt.full_line or nxt.begin_line != group[-1].end_line + 1:
                break
            group.append(nxt)
            j += 1

        # Split CML head + cml+ continuations from trailing plain comments
        if _CML_HEAD.match(group[0].text.strip()):
            cml_end = 1
            while cml_end < len(group) and _CML_CONT.match(group[cml_end].text.strip()):
                cml_end += 1
            cml_cluster = _CommentCluster(parts=group[:cml_end])
            _annotate_cml(cml_cluster)
            clusters.append(cml_cluster)
            for plain in group[cml_end:]:
                clusters.append(_CommentCluster(parts=[plain]))
        else:
            clusters.append(_CommentCluster(parts=group))
        i = j
    return clusters


def _blank_between(index: SourceIndex, end_line: int, begin_line: int) -> bool:
    """True if a blank line exists strictly between ``end_line`` and ``begin_line``."""
    if begin_line <= end_line + 1:
        return False
    for ln in range(end_line + 1, begin_line):
        if index.line_text(ln).strip() == "":
            return True
    return False


def _frag_begin_line(frag: Any) -> int | None:
    body = getattr(frag, "body", None)
    if body is not None and hasattr(body, "beginLine"):
        return int(body.beginLine)
    if hasattr(frag, "beginLine"):
        return int(frag.beginLine)
    return None


def _frag_end_line(frag: Any) -> int | None:
    body = getattr(frag, "body", None)
    if body is not None and hasattr(body, "endLine"):
        return int(body.endLine)
    if hasattr(frag, "endLine"):
        return int(frag.endLine)
    return None


def _make_attached(cluster: _CommentCluster) -> Any:
    if cluster.is_cml:
        return _CMLRawComment(cluster)
    return _AttachedComment(cluster)


def _make_suite_item(cluster: _CommentCluster) -> Any:
    if cluster.is_cml:
        return _CMLRawComment(cluster)
    return _IndependentCommentFrag(cluster)


def _set_leading(frag: Any, cluster: _CommentCluster) -> None:
    obj = _make_attached(cluster)
    if cluster.is_cml:
        frag.leadingCMLComments.append(obj)
        return
    existing = getattr(frag, "leadingComment", None)
    if existing is None:
        frag.leadingComment = obj
    elif isinstance(existing, _AttachedComment) and isinstance(obj, _AttachedComment):
        existing.extend_with(obj)
    else:
        frag.leadingComment = obj


def _set_side(frag: Any, cluster: _CommentCluster) -> None:
    obj = _make_attached(cluster)
    if cluster.is_cml:
        frag.sideCMLComments.append(obj)
    else:
        frag.sideComment = obj


def _attach_side_to_frag(frag: Any, clusters: list[_CommentCluster]) -> None:
    """Attach side comments on the fragment header line (``beginLine``)."""
    bln = _frag_begin_line(frag)
    if bln is None:
        return
    for cluster in clusters:
        if cluster.consumed or cluster.parts[0].full_line:
            continue
        if cluster.begin_line == bln:
            _set_side(frag, cluster)
            cluster.consumed = True


def _structural_targets(frag: Any) -> list[Any]:
    """Fragments that may own leading/side comments (headers), depth-first headers."""
    targets = [frag]
    for dec in getattr(frag, "decorators", []) or []:
        targets.append(dec)
    for part in getattr(frag, "parts", []) or []:
        targets.append(part)
    else_part = getattr(frag, "elsePart", None)
    if else_part is not None:
        targets.append(else_part)
    for ep in getattr(frag, "exceptParts", []) or []:
        targets.append(ep)
    finally_part = getattr(frag, "finallyPart", None)
    if finally_part is not None:
        targets.append(finally_part)
    return targets


def _recurse_nested(index: SourceIndex, frag: Any, clusters: list[_CommentCluster]) -> None:
    # Side/leading on nested structural headers (decorators, cases, except, …)
    for target in _structural_targets(frag)[1:]:  # skip self (already handled)
        _attach_side_to_frag(target, clusters)
        _attach_leading_block(index, target, clusters)

    if getattr(frag, "nsuite", None):
        _attach_to_suite(index, frag.nsuite, clusters, promote_trailing=False)
    for part in getattr(frag, "parts", []) or []:
        if getattr(part, "nsuite", None):
            _attach_to_suite(index, part.nsuite, clusters, promote_trailing=False)
    else_part = getattr(frag, "elsePart", None)
    if else_part is not None and getattr(else_part, "nsuite", None):
        _attach_to_suite(index, else_part.nsuite, clusters, promote_trailing=False)
    for ep in getattr(frag, "exceptParts", []) or []:
        if getattr(ep, "nsuite", None):
            _attach_to_suite(index, ep.nsuite, clusters, promote_trailing=False)
    finally_part = getattr(frag, "finallyPart", None)
    if finally_part is not None and getattr(finally_part, "nsuite", None):
        _attach_to_suite(index, finally_part.nsuite, clusters, promote_trailing=False)


def _attach_leading_block(index: SourceIndex, frag: Any, clusters: list[_CommentCluster]) -> None:
    """Attach contiguous full-line comment block ending at ``frag.beginLine - 1``."""
    bln = _frag_begin_line(frag)
    if bln is None:
        return
    by_end = {
        c.end_line: c
        for c in clusters
        if (not c.consumed) and c.parts[0].full_line and c.end_line < bln and not _blank_between(index, c.end_line, bln)
    }
    line_cursor = bln - 1
    leading_block: list[_CommentCluster] = []
    while line_cursor in by_end:
        cluster = by_end[line_cursor]
        leading_block.append(cluster)
        line_cursor = cluster.begin_line - 1
    leading_block.reverse()
    for cluster in leading_block:
        _set_leading(frag, cluster)
        cluster.consumed = True


def _attach_to_suite(
    index: SourceIndex,
    suite: list[Any],
    clusters: list[_CommentCluster],
    *,
    promote_trailing: bool = True,
) -> None:
    """Attach leading/side comments to suite items; insert independent ones."""
    for frag in suite:
        _attach_side_to_frag(frag, clusters)

    new_suite: list[Any] = []
    for frag in suite:
        bln = _frag_begin_line(frag)
        if bln is None:
            new_suite.append(frag)
            _recurse_nested(index, frag, clusters)
            continue

        # Independent full-line clusters strictly before this frag with a blank gap
        for cluster in clusters:
            if cluster.consumed or not cluster.parts[0].full_line:
                continue
            if cluster.end_line >= bln:
                continue
            if _blank_between(index, cluster.end_line, bln):
                new_suite.append(_make_suite_item(cluster))
                cluster.consumed = True

        # Prefer decorator leading over function/class leading when present
        decorators = getattr(frag, "decorators", None) or []
        if decorators:
            _attach_leading_block(index, decorators[0], clusters)
        _attach_leading_block(index, frag, clusters)
        new_suite.append(frag)
        _recurse_nested(index, frag, clusters)

    if promote_trailing:
        for cluster in clusters:
            if not cluster.consumed and cluster.parts[0].full_line:
                new_suite.append(_make_suite_item(cluster))
                cluster.consumed = True

    suite[:] = new_suite


class _LineBody:
    """Minimal body-like object for bang/encoding lines."""

    def __init__(self, begin: int, end: int, begin_line: int, end_line: int, begin_pos: int, end_pos: int) -> None:
        self.begin = begin
        self.end = end
        self.beginLine = begin_line
        self.endLine = end_line
        self.beginPos = begin_pos
        self.endPos = end_pos

    def getLineRange(self) -> tuple[int, int]:
        return (self.beginLine, self.endLine)

    def getAbsPosRange(self) -> tuple[int, int]:
        return (self.begin, self.end)


def detect_bang_and_encoding(source: str, index: SourceIndex) -> tuple[_LineBody | None, _LineBody | None]:
    """Return (bangLine, encodingLine) bodies when present."""
    lines = source.split("\n")
    bang = None
    enc = None
    if lines and lines[0].startswith("#!"):
        end = len(lines[0])
        bang = _LineBody(0, end, 1, 1, 1, end + 1)
    for ln_i, line in enumerate(lines[:2], start=1):
        if _ENCODING_COOKIE.match(line):
            begin = index.abs_char_pos(ln_i, 0)
            end = begin + len(line)
            enc = _LineBody(begin, end, ln_i, ln_i, 1, len(line) + 1)
            break
    return bang, enc


def bind_comments(control_flow: Any, source: str, index: SourceIndex) -> None:
    """Attach comments/CML to ``control_flow`` and nested suites (T026)."""
    bang, enc = detect_bang_and_encoding(source, index)
    control_flow.bangLine = bang
    control_flow.encodingLine = enc

    comments, tok_warnings = collect_token_comments(source, index)
    for msg in tok_warnings:
        control_flow.warnings.append((1, -1, msg))

    filtered: list[_TokComment] = []
    for c in comments:
        if bang is not None and c.begin_line == 1 and c.text.startswith("#!"):
            continue
        if enc is not None and c.begin_line == enc.beginLine and _ENCODING_COOKIE.match(c.line_content):
            continue
        filtered.append(c)

    clusters = _build_clusters(filtered)
    _attach_to_suite(index, control_flow.nsuite, clusters, promote_trailing=True)

    # Module-leading: unconsumed clusters immediately above first code item
    first_bln = None
    for frag in control_flow.nsuite:
        if getattr(frag, "kind", None) in (COMMENT_FRAGMENT, CML_COMMENT_FRAGMENT):
            continue
        first_bln = _frag_begin_line(frag)
        if first_bln is not None:
            break
    if first_bln is not None:
        by_end = {
            c.end_line: c
            for c in clusters
            if (not c.consumed)
            and c.parts[0].full_line
            and c.end_line < first_bln
            and not _blank_between(index, c.end_line, first_bln)
        }
        line_cursor = first_bln - 1
        leading_block: list[_CommentCluster] = []
        while line_cursor in by_end:
            cluster = by_end[line_cursor]
            leading_block.append(cluster)
            line_cursor = cluster.begin_line - 1
        leading_block.reverse()
        for cluster in leading_block:
            obj = _make_attached(cluster)
            if cluster.is_cml:
                control_flow.leadingCMLComments.append(obj)
            else:
                existing = getattr(control_flow, "leadingComment", None)
                if existing is None:
                    control_flow.leadingComment = obj
                elif isinstance(existing, _AttachedComment) and isinstance(obj, _AttachedComment):
                    existing.extend_with(obj)
                else:
                    control_flow.leadingComment = obj
            cluster.consumed = True

    # Remaining full-line → independent; never promote side comments to independent
    for cluster in list(clusters):
        if cluster.consumed:
            continue
        if cluster.parts[0].full_line:
            control_flow.nsuite.append(_make_suite_item(cluster))
            cluster.consumed = True
        else:
            control_flow.warnings.append(
                (
                    cluster.begin_line,
                    cluster.parts[0].begin_pos,
                    "unattached side comment (no matching fragment header)",
                )
            )
            cluster.consumed = True
