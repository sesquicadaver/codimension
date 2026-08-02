# -*- coding: utf-8 -*-
#
# codimension - pure Python control flow parser (ast-based)
# Copyright (C) 2010-2025  Sergey Satskiy <sergey.satskiy@gmail.com>
#
# Fallback for cdmcfparser when C extension unavailable (Python 3.11+).
# Builds fragment tree from Python AST.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Pure-Python cdmcfparser replacement using ast module."""

from __future__ import annotations

import ast
import tokenize
from typing import Any

from parsers.comment_binder import bind_comments
from parsers.source_spans import SourceIndex

# Fragment type constants (from cflowfragmenttypes.hpp)
UNDEFINED_FRAGMENT = -1
FRAGMENT = 0
BANG_LINE_FRAGMENT = 1
ENCODING_LINE_FRAGMENT = 2
COMMENT_FRAGMENT = 3
DOCSTRING_FRAGMENT = 4
DECORATOR_FRAGMENT = 5
CODEBLOCK_FRAGMENT = 6
FUNCTION_FRAGMENT = 7
CLASS_FRAGMENT = 8
BREAK_FRAGMENT = 9
CONTINUE_FRAGMENT = 10
RETURN_FRAGMENT = 11
RAISE_FRAGMENT = 12
ASSERT_FRAGMENT = 13
SYSEXIT_FRAGMENT = 14
WHILE_FRAGMENT = 15
FOR_FRAGMENT = 16
IMPORT_FRAGMENT = 17
ELIF_PART_FRAGMENT = 18
IF_FRAGMENT = 19
WITH_FRAGMENT = 20
EXCEPT_PART_FRAGMENT = 21
TRY_FRAGMENT = 22
ANNOTATION_FRAGMENT = 23
ARGUMENT_FRAGMENT = 24
MATCH_FRAGMENT = 25
CASE_PART_FRAGMENT = 26
TRY_STAR_FRAGMENT = 27
CML_COMMENT_FRAGMENT = 63
CONTROL_FLOW_FRAGMENT = 64

VERSION = "2.5.0-ast"
CML_VERSION = "1.0"


def _abs_pos(source: str, lineno: int, col_offset: int) -> int:
    """Compute 0-based absolute character position (UTF-8-aware)."""
    return SourceIndex.build(source).abs_char_pos(lineno, col_offset)


def _pos(node: ast.AST, source: str, index: SourceIndex | None = None) -> tuple[int, int, int, int, int, int]:
    """Return (begin, end, beginLine, endLine, beginPos, endPos) — exclusive end."""
    idx = index if index is not None else SourceIndex.build(source)
    return idx.node_span(node)


class _Body:
    """Fragment body with position info. Compatible with C++ Fragment."""

    def __init__(
        self,
        begin: int,
        end: int,
        begin_line: int,
        end_line: int,
        begin_pos: int,
        end_pos: int,
    ) -> None:
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


class _NameContent:
    """Name wrapper with getContent() for C++ Fragment compatibility."""

    def __init__(self, content: str) -> None:
        self._content = content

    def getContent(self) -> str:
        return self._content


class _FragmentBase:
    """Base for all fragments. Has kind, body, comment placeholders."""

    def __init__(
        self,
        kind: int,
        begin: int,
        end: int,
        bln: int,
        eln: int,
        bpos: int,
        epos: int,
    ) -> None:
        self.kind = kind
        self.body = _Body(begin, end, bln, eln, bpos, epos)
        self.leadingComment: Any = None
        self.sideComment: Any = None
        self.leadingCMLComments: list[Any] = []
        self.sideCMLComments: list[Any] = []

    @property
    def suite(self) -> list[_FragmentBase]:
        """Alias for nsuite - flow UI uses .suite."""
        return getattr(self, "nsuite", [])

    def getLineRange(self) -> tuple[int, int]:
        return self.body.getLineRange()

    def getAbsPosRange(self) -> tuple[int, int]:
        return self.body.getAbsPosRange()

    def getDisplayValue(self) -> str:
        return ""


class _ElifPart(_FragmentBase):
    """If/elif/else branch. condition is None for else."""

    def __init__(
        self,
        begin: int,
        end: int,
        bln: int,
        eln: int,
        bpos: int,
        epos: int,
        condition: _Body | None = None,
        display_value: str = "",
    ) -> None:
        super().__init__(ELIF_PART_FRAGMENT, begin, end, bln, eln, bpos, epos)
        self.condition = condition
        self.nsuite: list[_FragmentBase] = []
        self._display_value = display_value

    def getDisplayValue(self) -> str:
        return self._display_value


class _CodeBlock(_FragmentBase):
    """Simple statement block (may flag comprehensions — T027)."""

    def __init__(
        self,
        begin: int,
        end: int,
        bln: int,
        eln: int,
        bpos: int,
        epos: int,
        display_value: str = "",
    ) -> None:
        super().__init__(CODEBLOCK_FRAGMENT, begin, end, bln, eln, bpos, epos)
        self.isComprehension: bool = False
        self._display_value = display_value

    def getDisplayValue(self) -> str:
        return self._display_value


class _ImportFrag(_FragmentBase):
    """Import statement."""

    def __init__(
        self,
        begin: int,
        end: int,
        bln: int,
        eln: int,
        bpos: int,
        epos: int,
        display_value: str = "",
        from_part: _Body | None = None,
        what_part: _Body | None = None,
    ) -> None:
        super().__init__(IMPORT_FRAGMENT, begin, end, bln, eln, bpos, epos)
        self._display_value = display_value
        self.fromPart = from_part
        self.whatPart = what_part

    def getDisplayValue(self) -> str:
        return self._display_value


class _ReturnFrag(_FragmentBase):
    """Return statement."""

    def __init__(
        self,
        begin: int,
        end: int,
        bln: int,
        eln: int,
        bpos: int,
        epos: int,
        value: _Body | None = None,
    ) -> None:
        super().__init__(RETURN_FRAGMENT, begin, end, bln, eln, bpos, epos)
        self.value = value


class _RaiseFrag(_FragmentBase):
    """Raise statement."""

    def __init__(
        self,
        begin: int,
        end: int,
        bln: int,
        eln: int,
        bpos: int,
        epos: int,
        value: _Body | None = None,
    ) -> None:
        super().__init__(RAISE_FRAGMENT, begin, end, bln, eln, bpos, epos)
        self.value = value


class _BreakFrag(_FragmentBase):
    """Break statement."""

    def __init__(self, begin: int, end: int, bln: int, eln: int, bpos: int, epos: int) -> None:
        super().__init__(BREAK_FRAGMENT, begin, end, bln, eln, bpos, epos)


class _ContinueFrag(_FragmentBase):
    """Continue statement."""

    def __init__(self, begin: int, end: int, bln: int, eln: int, bpos: int, epos: int) -> None:
        super().__init__(CONTINUE_FRAGMENT, begin, end, bln, eln, bpos, epos)


class _AssertFrag(_FragmentBase):
    """Assert statement. C++ cdmcfparser API: flowui expects ref.test."""

    def __init__(
        self,
        begin: int,
        end: int,
        bln: int,
        eln: int,
        bpos: int,
        epos: int,
        test: _Body | None = None,
        message: _Body | None = None,
    ) -> None:
        super().__init__(ASSERT_FRAGMENT, begin, end, bln, eln, bpos, epos)
        self.test = test
        self.message = message


class _SysExitFrag(_FragmentBase):
    """sys.exit() call."""

    def __init__(
        self,
        begin: int,
        end: int,
        bln: int,
        eln: int,
        bpos: int,
        epos: int,
        arg: _Body | None = None,
    ) -> None:
        super().__init__(SYSEXIT_FRAGMENT, begin, end, bln, eln, bpos, epos)
        self.arg = arg
        self.actualArg = arg


class _FunctionFrag(_FragmentBase):
    """Function definition."""

    def __init__(self, begin: int, end: int, bln: int, eln: int, bpos: int, epos: int) -> None:
        super().__init__(FUNCTION_FRAGMENT, begin, end, bln, eln, bpos, epos)
        self.name: _NameContent | None = None
        self.decorators: list[_FragmentBase] = []
        self.nsuite: list[_FragmentBase] = []
        self.docstring: _DocstringFrag | None = None
        self.isAsync: bool = False

    def getDisplayValue(self) -> str:
        if self.name is not None:
            return self.name.getContent()
        return ""


class _ClassFrag(_FragmentBase):
    """Class definition."""

    def __init__(self, begin: int, end: int, bln: int, eln: int, bpos: int, epos: int) -> None:
        super().__init__(CLASS_FRAGMENT, begin, end, bln, eln, bpos, epos)
        self.name: _NameContent | None = None
        self.decorators: list[_FragmentBase] = []
        self.nsuite: list[_FragmentBase] = []
        self.docstring: _DocstringFrag | None = None

    def getDisplayValue(self) -> str:
        if self.name is not None:
            return self.name.getContent()
        return ""


class _ForFrag(_FragmentBase):
    """For / async for loop."""

    def __init__(self, begin: int, end: int, bln: int, eln: int, bpos: int, epos: int) -> None:
        super().__init__(FOR_FRAGMENT, begin, end, bln, eln, bpos, epos)
        self.condition: _Body | None = None
        self.nsuite: list[_FragmentBase] = []
        self.elsePart: _ElifPart | None = None
        self.isAsync: bool = False


class _WhileFrag(_FragmentBase):
    """While loop."""

    def __init__(self, begin: int, end: int, bln: int, eln: int, bpos: int, epos: int) -> None:
        super().__init__(WHILE_FRAGMENT, begin, end, bln, eln, bpos, epos)
        self.condition: _Body | None = None
        self.nsuite: list[_FragmentBase] = []
        self.elsePart: _ElifPart | None = None


class _WithFrag(_FragmentBase):
    """With / async with statement."""

    def __init__(self, begin: int, end: int, bln: int, eln: int, bpos: int, epos: int) -> None:
        super().__init__(WITH_FRAGMENT, begin, end, bln, eln, bpos, epos)
        self.nsuite: list[_FragmentBase] = []
        self.isAsync: bool = False
        self.withItems: list[str] = []


class _ExceptPart(_FragmentBase):
    """Except clause."""

    def __init__(
        self,
        begin: int,
        end: int,
        bln: int,
        eln: int,
        bpos: int,
        epos: int,
        clause: _Body | None = None,
    ) -> None:
        super().__init__(EXCEPT_PART_FRAGMENT, begin, end, bln, eln, bpos, epos)
        self.clause = clause
        self.nsuite: list[_FragmentBase] = []


class _TryFrag(_FragmentBase):
    """Try / try-star statement."""

    def __init__(
        self,
        begin: int,
        end: int,
        bln: int,
        eln: int,
        bpos: int,
        epos: int,
        kind: int = TRY_FRAGMENT,
    ) -> None:
        super().__init__(kind, begin, end, bln, eln, bpos, epos)
        self.nsuite: list[_FragmentBase] = []
        self.exceptParts: list[_ExceptPart] = []
        self.elsePart: _ElifPart | None = None
        self.finallyPart: _ElifPart | None = None


class _CasePart(_FragmentBase):
    """One ``case`` arm inside ``match``."""

    def __init__(
        self,
        begin: int,
        end: int,
        bln: int,
        eln: int,
        bpos: int,
        epos: int,
        display_value: str = "",
    ) -> None:
        super().__init__(CASE_PART_FRAGMENT, begin, end, bln, eln, bpos, epos)
        self.nsuite: list[_FragmentBase] = []
        self._display_value = display_value

    def getDisplayValue(self) -> str:
        return self._display_value


class _MatchFrag(_FragmentBase):
    """``match`` statement; ``parts`` holds case arms."""

    def __init__(self, begin: int, end: int, bln: int, eln: int, bpos: int, epos: int) -> None:
        super().__init__(MATCH_FRAGMENT, begin, end, bln, eln, bpos, epos)
        self.parts: list[_CasePart] = []
        self._display_value = ""

    def getDisplayValue(self) -> str:
        return self._display_value or "match"


class _IfFrag(_FragmentBase):
    """If/elif/else statement. parts = list of ElifPart."""

    def __init__(self, begin: int, end: int, bln: int, eln: int, bpos: int, epos: int) -> None:
        super().__init__(IF_FRAGMENT, begin, end, bln, eln, bpos, epos)
        self.parts: list[_ElifPart] = []


class _ControlFlow(_FragmentBase):
    """Top-level control flow container."""

    def __init__(self, source: str):
        lines = source.split("\n")
        end_ln = len(lines) if lines else 1
        end_pos = len(lines[-1]) + 1 if lines else 1
        super().__init__(CONTROL_FLOW_FRAGMENT, 0, max(0, len(source) - 1), 1, end_ln, 1, end_pos)
        self.nsuite: list[_FragmentBase] = []
        self.docstring: _DocstringFrag | None = None
        self.leadingComment: Any = None
        self.leadingCMLComments: list = []
        # C++ cdmcfparser API: scopeitems.getLineDistance/getDistance expect these
        self.encodingLine: _Body | None = None
        self.bangLine: _Body | None = None
        # flowuiwidget expects list of (line, col, msg) tuples
        self.errors: list[tuple[int, int, str]] = []
        self.warnings: list[tuple[int, int, str]] = []

    def __str__(self) -> str:
        """String representation for formatFlow() - uses < > for nesting.
        formatFlow requires '<' before any '\\n' (shifts must be non-empty)."""
        return self._str_suite(self.nsuite)

    def _str_suite(self, suite: list[_FragmentBase]) -> str:
        """Produce format: Name<\\ncontent\\n> for nested, Name for leaf."""
        chunks = []
        for item in suite:
            kind_name = _KIND_NAMES.get(item.kind, "Fragment")
            inner = []
            if hasattr(item, "nsuite") and item.nsuite:
                inner.append(self._str_suite(item.nsuite))
            if hasattr(item, "parts") and item.parts:
                for p in item.parts:
                    inner.append("part")
                    if getattr(p, "nsuite", None):
                        inner.append(self._str_suite(p.nsuite))
            if hasattr(item, "elsePart") and item.elsePart and item.elsePart.nsuite:
                inner.append("else")
                inner.append(self._str_suite(item.elsePart.nsuite))
            if hasattr(item, "exceptParts") and item.exceptParts:
                for ep in item.exceptParts:
                    if getattr(ep, "nsuite", None):
                        inner.append(self._str_suite(ep.nsuite))
            if hasattr(item, "finallyPart") and item.finallyPart and item.finallyPart.nsuite:
                inner.append("finally")
                inner.append(self._str_suite(item.finallyPart.nsuite))
            if inner:
                chunks.append(kind_name + "<\n" + "\n".join(inner) + "\n>")
            else:
                chunks.append(kind_name)
        # No newline between chunks: formatFlow requires shifts non-empty on \n
        return "".join(chunks)


_KIND_NAMES = {
    COMMENT_FRAGMENT: "Comment",
    CODEBLOCK_FRAGMENT: "CodeBlock",
    FUNCTION_FRAGMENT: "Function",
    CLASS_FRAGMENT: "Class",
    FOR_FRAGMENT: "For",
    WHILE_FRAGMENT: "While",
    IF_FRAGMENT: "If",
    TRY_FRAGMENT: "Try",
    WITH_FRAGMENT: "With",
    RETURN_FRAGMENT: "Return",
    IMPORT_FRAGMENT: "Import",
    MATCH_FRAGMENT: "Match",
    CASE_PART_FRAGMENT: "Case",
    TRY_STAR_FRAGMENT: "TryStar",
    CML_COMMENT_FRAGMENT: "CML",
    DOCSTRING_FRAGMENT: "Docstring",
    DECORATOR_FRAGMENT: "Decorator",
    BANG_LINE_FRAGMENT: "BangLine",
    ENCODING_LINE_FRAGMENT: "EncodingLine",
}


class _DocstringFrag:
    """Docstring fragment for getDisplayValue().

    CML validation expects leadingCMLComments and sideCMLComments;
    flow_ast docstrings have none, so these are empty lists.
    """

    def __init__(self, text: str | None) -> None:
        self._text = text or ""
        self.leadingCMLComments: list = []
        self.sideCMLComments: list = []

    def getDisplayValue(self) -> str:
        return self._text


class _FlowBuilder(ast.NodeVisitor):
    """Builds fragment tree from AST."""

    def __init__(self, source: str):
        self.source = source
        self.index = SourceIndex.build(source)
        self.control_flow = _ControlFlow(source)

    def _pos(self, node: ast.AST) -> tuple[int, int, int, int, int, int]:
        return _pos(node, self.source, self.index)

    def _make_body(self, node: ast.AST) -> _Body:
        b, e, bln, eln, bpos, epos = self._pos(node)
        return _Body(b, e, bln, eln, bpos, epos)

    def _body_from_abs_range(self, begin: int, end: int) -> _Body:
        """Build _Body from inclusive 0-based absolute source positions."""
        if begin < 0:
            begin = 0
        if end < begin:
            end = begin
        prefix = self.source[:begin]
        bln = prefix.count("\n") + 1
        last_nl = prefix.rfind("\n")
        bpos = begin - last_nl
        prefix_end = self.source[: end + 1]
        eln = prefix_end.count("\n") + 1
        last_nl_e = prefix_end.rfind("\n")
        epos = end - last_nl_e if last_nl_e >= 0 else end + 1
        return _Body(begin, end, bln, eln, bpos, epos)

    def _extract_module_docstring(self, node: ast.Module) -> None:
        """Extract module docstring from first Expr(Constant(str))."""
        doc = ast.get_docstring(node)
        if doc:
            self.control_flow.docstring = _DocstringFrag(doc)

    @staticmethod
    def _is_docstring_stmt(stmt: ast.AST) -> bool:
        """True if ``stmt`` is a standalone string expression used as a docstring."""
        return (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str)
        )

    def _attach_docstring(self, node: ast.AST, frag: Any) -> list[ast.stmt]:
        """Set ``frag.docstring`` from ``node`` and return body without docstring stmt."""
        doc = ast.get_docstring(node)  # type: ignore[arg-type]
        body = list(getattr(node, "body", []) or [])
        if doc and body and self._is_docstring_stmt(body[0]):
            frag.docstring = _DocstringFrag(doc)
            return body[1:]
        return body

    def _visit_suite(
        self,
        node: list[ast.stmt],
        suite_list: list[_FragmentBase],
    ) -> None:
        """Visit suite (list of statements) and append to suite_list."""
        for stmt in node:
            frag = self._stmt_to_fragment(stmt)
            if frag is not None:
                suite_list.append(frag)

    def _stmt_to_fragment(self, node: ast.AST) -> _FragmentBase | None:
        """Convert AST stmt to fragment. Returns None for unsupported."""
        if isinstance(node, ast.FunctionDef):
            return self._visit_function(node)
        if isinstance(node, ast.AsyncFunctionDef):
            return self._visit_function(node)
        if isinstance(node, ast.ClassDef):
            return self._visit_class(node)
        if isinstance(node, ast.For):
            return self._visit_for(node)
        if isinstance(node, ast.AsyncFor):
            return self._visit_for(node)
        if isinstance(node, ast.While):
            return self._visit_while(node)
        if isinstance(node, ast.If):
            return self._visit_if(node)
        if isinstance(node, ast.With):
            return self._visit_with(node)
        if isinstance(node, ast.AsyncWith):
            return self._visit_with(node)
        if isinstance(node, ast.Try):
            return self._visit_try(node)
        try_star = getattr(ast, "TryStar", None)
        if try_star is not None and isinstance(node, try_star):
            return self._visit_try(node, kind=TRY_STAR_FRAGMENT)
        if isinstance(node, ast.Match):
            return self._visit_match(node)
        if isinstance(node, ast.Return):
            return self._visit_return(node)
        if isinstance(node, ast.Raise):
            return self._visit_raise(node)
        if isinstance(node, ast.Break):
            return self._visit_break(node)
        if isinstance(node, ast.Continue):
            return self._visit_continue(node)
        if isinstance(node, ast.Assert):
            return self._visit_assert(node)
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return self._visit_import(node)
        if isinstance(node, ast.Expr):
            if isinstance(node.value, ast.Call):
                return self._visit_sysexit(node)
        # Other statements -> code block
        return self._visit_code_block(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> _FunctionFrag:
        """Build Function fragment."""
        b, e, bln, eln, bpos, epos = self._pos(node)
        frag = _FunctionFrag(b, e, bln, eln, bpos, epos)
        frag.name = _NameContent(node.name)
        frag.isAsync = isinstance(node, ast.AsyncFunctionDef)
        for dec in node.decorator_list:
            db, de, dbln, deln, dbpos, depos = self._pos(dec)
            dec_frag = _FragmentBase(DECORATOR_FRAGMENT, db, de, dbln, deln, dbpos, depos)
            frag.decorators.append(dec_frag)
        self._visit_suite(self._attach_docstring(node, frag), frag.nsuite)
        return frag

    def _visit_class(self, node: ast.ClassDef) -> _ClassFrag:
        """Build Class fragment."""
        b, e, bln, eln, bpos, epos = self._pos(node)
        frag = _ClassFrag(b, e, bln, eln, bpos, epos)
        frag.name = _NameContent(node.name)
        for dec in node.decorator_list:
            db, de, dbln, deln, dbpos, depos = self._pos(dec)
            dec_frag = _FragmentBase(DECORATOR_FRAGMENT, db, de, dbln, deln, dbpos, depos)
            frag.decorators.append(dec_frag)
        self._visit_suite(self._attach_docstring(node, frag), frag.nsuite)
        return frag

    def _visit_for(self, node: ast.For | ast.AsyncFor) -> _ForFrag:
        """Build For / async for fragment (T025)."""
        b, e, bln, eln, bpos, epos = self._pos(node)
        frag = _ForFrag(b, e, bln, eln, bpos, epos)
        frag.isAsync = isinstance(node, ast.AsyncFor)
        frag.condition = self._make_body(node.iter)
        self._visit_suite(node.body, frag.nsuite)
        if node.orelse:
            else_part = self._make_elif_part(None, node.orelse)
            frag.elsePart = else_part
        return frag

    def _visit_while(self, node: ast.While) -> _WhileFrag:
        """Build While fragment."""
        b, e, bln, eln, bpos, epos = self._pos(node)
        frag = _WhileFrag(b, e, bln, eln, bpos, epos)
        frag.condition = self._make_body(node.test)
        self._visit_suite(node.body, frag.nsuite)
        if node.orelse:
            else_part = self._make_elif_part(None, node.orelse)
            frag.elsePart = else_part
        return frag

    def _header_line_above(self, body_lineno: int, keywords: tuple[str, ...]) -> tuple[int, int, int] | None:
        """Find ``else``/``finally`` header line just above a suite."""
        for ln in range(body_lineno - 1, 0, -1):
            text = self.index.line_text(ln).strip()
            if not text:
                continue
            if text.startswith("#"):
                continue
            for kw in keywords:
                if text == f"{kw}:" or text.startswith(f"{kw}:") or text.startswith(f"{kw} "):
                    return self.index.abs_char_pos(ln, 0), ln, 1
            break
        return None

    def _make_elif_part(
        self,
        condition_node: ast.expr | None,
        body: list[ast.stmt],
        *,
        else_keywords: tuple[str, ...] = ("else",),
    ) -> _ElifPart:
        """Build ElifPart from condition and body (span includes header line)."""
        if condition_node is not None:
            b, _, bln, _, bpos, _ = self._pos(condition_node)
        elif body:
            hdr = self._header_line_above(body[0].lineno, else_keywords)
            if hdr is not None:
                b, bln, bpos = hdr
            else:
                b, _, bln, _, bpos, _ = self._pos(body[0])
        else:
            b, bln, bpos = 0, 1, 1
        if body:
            _, e, _, eln, _, epos = self._pos(body[-1])
        elif condition_node is not None:
            _, e, _, eln, _, epos = self._pos(condition_node)
        else:
            e, eln, epos = b, bln, bpos
        cond = self._make_body(condition_node) if condition_node else None
        if condition_node is None:
            display_value = else_keywords[0] if else_keywords else "else"
        elif self.source and cond:
            display_value = self.source[cond.begin : cond.end].strip().rstrip(":")
        else:
            display_value = ""
        part = _ElifPart(b, e, bln, eln, bpos, epos, condition=cond, display_value=display_value)
        self._visit_suite(body, part.nsuite)
        return part

    def _visit_if(self, node: ast.If) -> _IfFrag:
        """Build If fragment with parts (if/elif/else)."""
        b, e, bln, eln, bpos, epos = self._pos(node)
        frag = _IfFrag(b, e, bln, eln, bpos, epos)
        # if part
        frag.parts.append(self._make_elif_part(node.test, node.body))
        # elif parts
        curr = node
        while curr.orelse and len(curr.orelse) == 1 and isinstance(curr.orelse[0], ast.If):
            curr = curr.orelse[0]
            frag.parts.append(self._make_elif_part(curr.test, curr.body))
        # else part
        if curr.orelse:
            frag.parts.append(self._make_elif_part(None, curr.orelse))
        return frag

    def _visit_with(self, node: ast.With | ast.AsyncWith) -> _WithFrag:
        """Build With / async with fragment with context items (T025)."""
        b, e, bln, eln, bpos, epos = self._pos(node)
        frag = _WithFrag(b, e, bln, eln, bpos, epos)
        frag.isAsync = isinstance(node, ast.AsyncWith)
        for item in node.items:
            try:
                ctx = ast.unparse(item.context_expr) if hasattr(ast, "unparse") else ""
            except Exception:
                ctx = ""
            if item.optional_vars is not None:
                try:
                    target = ast.unparse(item.optional_vars) if hasattr(ast, "unparse") else ""
                except Exception:
                    target = ""
                frag.withItems.append(f"{ctx} as {target}" if target else ctx)
            else:
                frag.withItems.append(ctx)
        self._visit_suite(node.body, frag.nsuite)
        return frag

    def _visit_try(self, node: ast.Try, kind: int = TRY_FRAGMENT) -> _TryFrag:
        """Build Try or TryStar fragment."""
        b, e, bln, eln, bpos, epos = self._pos(node)
        frag = _TryFrag(b, e, bln, eln, bpos, epos, kind=kind)
        self._visit_suite(node.body, frag.nsuite)
        for handler in node.handlers:
            hb, he, hbln, heln, hbpos, hepos = self._pos(handler)
            clause = self._make_body(handler.type) if handler.type else None
            exc_part = _ExceptPart(hb, he, hbln, heln, hbpos, hepos, clause=clause)
            self._visit_suite(handler.body, exc_part.nsuite)
            frag.exceptParts.append(exc_part)
        if node.orelse:
            frag.elsePart = self._make_elif_part(None, node.orelse, else_keywords=("else",))
        if node.finalbody:
            frag.finallyPart = self._make_elif_part(None, node.finalbody, else_keywords=("finally",))
        return frag

    def _visit_match(self, node: ast.Match) -> _MatchFrag:
        """Build Match fragment with Case parts (T023)."""
        b, e, bln, eln, bpos, epos = self._pos(node)
        frag = _MatchFrag(b, e, bln, eln, bpos, epos)
        try:
            subj = ast.unparse(node.subject) if hasattr(ast, "unparse") else ""
        except Exception:
            subj = ""
        frag._display_value = f"match {subj}:" if subj else "match"
        for case in node.cases:
            # Span from pattern (case header) through last body stmt
            cb, _, cbln, _, cbpos, _ = self._pos(case.pattern)
            if case.body:
                _, ce, _, celn, _, cepos = self._pos(case.body[-1])
            else:
                _, ce, _, celn, _, cepos = self._pos(case.pattern)
            try:
                pattern_src = ast.unparse(case.pattern) if hasattr(ast, "unparse") else "_"
            except (TypeError, ValueError, RecursionError):
                pattern_src = "_"
            display = f"case {pattern_src}:"
            part = _CasePart(cb, ce, cbln, celn, cbpos, cepos, display_value=display)
            self._visit_suite(case.body, part.nsuite)
            frag.parts.append(part)
        return frag

    def _visit_return(self, node: ast.Return) -> _ReturnFrag:
        """Build Return fragment."""
        b, e, bln, eln, bpos, epos = self._pos(node)
        val = self._make_body(node.value) if node.value else None
        return _ReturnFrag(b, e, bln, eln, bpos, epos, value=val)

    def _visit_raise(self, node: ast.Raise) -> _RaiseFrag:
        """Build Raise fragment."""
        b, e, bln, eln, bpos, epos = self._pos(node)
        val = self._make_body(node.exc) if node.exc else None
        return _RaiseFrag(b, e, bln, eln, bpos, epos, value=val)

    def _visit_break(self, node: ast.Break) -> _BreakFrag:
        """Build Break fragment."""
        b, e, bln, eln, bpos, epos = self._pos(node)
        return _BreakFrag(b, e, bln, eln, bpos, epos)

    def _visit_continue(self, node: ast.Continue) -> _ContinueFrag:
        """Build Continue fragment."""
        b, e, bln, eln, bpos, epos = self._pos(node)
        return _ContinueFrag(b, e, bln, eln, bpos, epos)

    def _visit_assert(self, node: ast.Assert) -> _AssertFrag:
        """Build Assert fragment."""
        b, e, bln, eln, bpos, epos = self._pos(node)
        tst = self._make_body(node.test) if node.test else None
        msg = self._make_body(node.msg) if node.msg else None
        return _AssertFrag(b, e, bln, eln, bpos, epos, test=tst, message=msg)

    def _visit_import(self, node: ast.Import | ast.ImportFrom) -> _ImportFrag:
        """Build Import fragment with display text and fromPart/whatPart."""
        b, e, bln, eln, bpos, epos = self._pos(node)
        display_value: str
        from_part: _Body | None = None
        what_part: _Body | None = None

        if isinstance(node, ast.Import):
            names = [alias.name if alias.asname is None else f"{alias.name} as {alias.asname}" for alias in node.names]
            display_value = "import " + ", ".join(names)
            what_part = _Body(b, e, bln, eln, bpos, epos)
        else:
            module = node.module or ""
            names = []
            for alias in node.names:
                if alias.asname is None:
                    names.append(alias.name)
                else:
                    names.append(f"{alias.name} as {alias.asname}")
            what_str = ", ".join(names)
            display_value = f"from {module} import {what_str}" if module else f"import {what_str}"
            if node.module:
                chunk = self.source[b:e]
                needle = f"from {module}"
                off = chunk.find(needle)
                if off >= 0:
                    mod_b = b + off + len("from ")
                    mod_e = mod_b + len(module) - 1
                    from_part = self._body_from_abs_range(mod_b, mod_e)
            what_part = _Body(b, e, bln, eln, bpos, epos)

        return _ImportFrag(
            b, e, bln, eln, bpos, epos, display_value=display_value, from_part=from_part, what_part=what_part
        )

    def _visit_sysexit(self, node: ast.Expr) -> _SysExitFrag | _CodeBlock | None:
        """Check for sys.exit() and build SysExit fragment if so."""
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            return None
        call = node.value
        if isinstance(call.func, ast.Attribute):
            if isinstance(call.func.value, ast.Name) and call.func.value.id == "sys" and call.func.attr == "exit":
                b, e, bln, eln, bpos, epos = self._pos(node)
                arg = self._make_body(call) if call.args else None
                return _SysExitFrag(b, e, bln, eln, bpos, epos, arg=arg)
        return self._visit_code_block(node)

    def _visit_code_block(self, node: ast.AST) -> _CodeBlock:
        """Build CodeBlock fragment for generic statement (T027 comprehensions flagged)."""
        b, e, bln, eln, bpos, epos = self._pos(node)
        display_value = self.source[b:e] if self.source and e >= b else ""
        frag = _CodeBlock(b, e, bln, eln, bpos, epos, display_value=display_value)
        frag.isComprehension = self._contains_comprehension(node)
        return frag

    @staticmethod
    def _contains_comprehension(node: ast.AST) -> bool:
        """True if ``node`` is or wraps a list/set/dict/generator comprehension."""
        comp_types = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
        if isinstance(node, ast.Expr) and isinstance(node.value, comp_types):
            return True
        if isinstance(node, ast.Assign):
            return any(isinstance(getattr(node, "value", None), t) for t in comp_types)
        if isinstance(node, ast.AnnAssign) and isinstance(getattr(node, "value", None), comp_types):
            return True
        return isinstance(node, comp_types)

    def visit(self, node: ast.AST | None) -> None:
        """Override to collect into control_flow.nsuite."""
        if node is None:
            return
        if isinstance(node, ast.Module):
            self._extract_module_docstring(node)
            body = list(node.body)
            if self.control_flow.docstring is not None and body and self._is_docstring_stmt(body[0]):
                body = body[1:]
            for stmt in body:
                self.visit(stmt)
            return
        frag = self._stmt_to_fragment(node)
        if frag is not None:
            self.control_flow.nsuite.append(frag)


def _build_control_flow(source: str, filename: str) -> _ControlFlow:
    """Parse source and build ControlFlow fragment tree."""
    try:
        tree = ast.parse(source, filename, mode="exec", type_comments=True)
    except SyntaxError as exc:
        cf = _ControlFlow(source)
        # flowuiwidget expects (line, col, msg) tuples
        line = getattr(exc, "lineno", -1)
        col = getattr(exc, "offset", -1)
        cf.errors.append((line, col, str(exc.msg) if exc.msg else "Syntax error"))
        return cf
    builder = _FlowBuilder(source)
    builder.visit(tree)
    bind_comments(builder.control_flow, source, builder.index)
    return builder.control_flow


def getControlFlowFromMemory(content: str) -> _ControlFlow:
    """Build control flow from string content."""
    return _build_control_flow(content, "<string>")


def getControlFlowFromFile(fileName: str) -> _ControlFlow:
    """Build control flow from file using PEP 263 encoding detection."""
    with tokenize.open(fileName) as f:
        return _build_control_flow(f.read(), fileName)
