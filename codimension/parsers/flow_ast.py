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
from typing import Any

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
CML_COMMENT_FRAGMENT = 63
CONTROL_FLOW_FRAGMENT = 64

VERSION = '2.5.0-ast'
CML_VERSION = '1.0'


def _abs_pos(source: str, lineno: int, col_offset: int) -> int:
    """Compute 0-based absolute position from line/col."""
    lines = source.split('\n')
    if lineno < 1:
        return 0
    return sum(len(line) + 1 for line in lines[:lineno - 1]) + col_offset


def _pos(node: ast.AST, source: str) -> tuple[int, int, int, int, int, int]:
    """Return (begin, end, beginLine, endLine, beginPos, endPos) for node."""
    ln = getattr(node, 'lineno', 1) or 1
    co = getattr(node, 'col_offset', 0) or 0
    eln = getattr(node, 'end_lineno', ln) or ln
    eco = getattr(node, 'end_col_offset', co) or co
    begin = _abs_pos(source, ln, co)
    end = _abs_pos(source, eln, eco)
    return begin, end, ln, eln, co + 1, eco + 1


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
        return getattr(self, 'nsuite', [])

    def getLineRange(self) -> tuple[int, int]:
        return self.body.getLineRange()

    def getAbsPosRange(self) -> tuple[int, int]:
        return self.body.getAbsPosRange()

    def getDisplayValue(self) -> str:
        return ''


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
        display_value: str = '',
    ) -> None:
        super().__init__(ELIF_PART_FRAGMENT, begin, end, bln, eln, bpos, epos)
        self.condition = condition
        self.nsuite: list[_FragmentBase] = []
        self._display_value = display_value

    def getDisplayValue(self) -> str:
        return self._display_value


class _CodeBlock(_FragmentBase):
    """Simple statement block."""

    def __init__(
        self,
        begin: int,
        end: int,
        bln: int,
        eln: int,
        bpos: int,
        epos: int,
        display_value: str = '',
    ) -> None:
        super().__init__(CODEBLOCK_FRAGMENT, begin, end, bln, eln, bpos, epos)
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
        display_value: str = '',
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

    def __init__(
        self, begin: int, end: int, bln: int, eln: int, bpos: int, epos: int
    ) -> None:
        super().__init__(BREAK_FRAGMENT, begin, end, bln, eln, bpos, epos)


class _ContinueFrag(_FragmentBase):
    """Continue statement."""

    def __init__(
        self, begin: int, end: int, bln: int, eln: int, bpos: int, epos: int
    ) -> None:
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

    def __init__(
        self, begin: int, end: int, bln: int, eln: int, bpos: int, epos: int
    ) -> None:
        super().__init__(FUNCTION_FRAGMENT, begin, end, bln, eln, bpos, epos)
        self.decorators: list[_FragmentBase] = []
        self.nsuite: list[_FragmentBase] = []
        self.docstring: _DocstringFrag | None = None

    def getDisplayValue(self) -> str:
        if hasattr(self, 'name') and self.name is not None:
            return self.name.getContent()
        return ''


class _ClassFrag(_FragmentBase):
    """Class definition."""

    def __init__(
        self, begin: int, end: int, bln: int, eln: int, bpos: int, epos: int
    ) -> None:
        super().__init__(CLASS_FRAGMENT, begin, end, bln, eln, bpos, epos)
        self.decorators: list[_FragmentBase] = []
        self.nsuite: list[_FragmentBase] = []
        self.docstring: _DocstringFrag | None = None

    def getDisplayValue(self) -> str:
        if hasattr(self, 'name') and self.name is not None:
            return self.name.getContent()
        return ''


class _ForFrag(_FragmentBase):
    """For loop."""

    def __init__(
        self, begin: int, end: int, bln: int, eln: int, bpos: int, epos: int
    ) -> None:
        super().__init__(FOR_FRAGMENT, begin, end, bln, eln, bpos, epos)
        self.condition: _Body | None = None
        self.nsuite: list[_FragmentBase] = []
        self.elsePart: _ElifPart | None = None


class _WhileFrag(_FragmentBase):
    """While loop."""

    def __init__(
        self, begin: int, end: int, bln: int, eln: int, bpos: int, epos: int
    ) -> None:
        super().__init__(WHILE_FRAGMENT, begin, end, bln, eln, bpos, epos)
        self.condition: _Body | None = None
        self.nsuite: list[_FragmentBase] = []
        self.elsePart: _ElifPart | None = None


class _WithFrag(_FragmentBase):
    """With statement."""

    def __init__(
        self, begin: int, end: int, bln: int, eln: int, bpos: int, epos: int
    ) -> None:
        super().__init__(WITH_FRAGMENT, begin, end, bln, eln, bpos, epos)
        self.nsuite: list[_FragmentBase] = []


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
    """Try statement."""

    def __init__(
        self, begin: int, end: int, bln: int, eln: int, bpos: int, epos: int
    ) -> None:
        super().__init__(TRY_FRAGMENT, begin, end, bln, eln, bpos, epos)
        self.nsuite: list[_FragmentBase] = []
        self.exceptParts: list[_ExceptPart] = []
        self.elsePart: _ElifPart | None = None
        self.finallyPart: _ElifPart | None = None


class _IfFrag(_FragmentBase):
    """If/elif/else statement. parts = list of ElifPart."""

    def __init__(
        self, begin: int, end: int, bln: int, eln: int, bpos: int, epos: int
    ) -> None:
        super().__init__(IF_FRAGMENT, begin, end, bln, eln, bpos, epos)
        self.parts: list[_ElifPart] = []


class _ControlFlow(_FragmentBase):
    """Top-level control flow container."""

    def __init__(self, source: str):
        lines = source.split('\n')
        end_ln = len(lines) if lines else 1
        end_pos = len(lines[-1]) + 1 if lines else 1
        super().__init__(CONTROL_FLOW_FRAGMENT, 0, max(0, len(source) - 1), 1,
                         end_ln, 1, end_pos)
        self.nsuite: list[_FragmentBase] = []
        self.docstring: _DocstringFrag | None = None
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
            kind_name = _KIND_NAMES.get(item.kind, 'Fragment')
            inner = []
            if hasattr(item, 'nsuite') and item.nsuite:
                inner.append(self._str_suite(item.nsuite))
            if hasattr(item, 'parts') and item.parts:
                for p in item.parts:
                    inner.append('part')
                    if getattr(p, 'nsuite', None):
                        inner.append(self._str_suite(p.nsuite))
            if hasattr(item, 'elsePart') and item.elsePart and item.elsePart.nsuite:
                inner.append('else')
                inner.append(self._str_suite(item.elsePart.nsuite))
            if hasattr(item, 'exceptParts') and item.exceptParts:
                for ep in item.exceptParts:
                    if getattr(ep, 'nsuite', None):
                        inner.append(self._str_suite(ep.nsuite))
            if hasattr(item, 'finallyPart') and item.finallyPart and item.finallyPart.nsuite:
                inner.append('finally')
                inner.append(self._str_suite(item.finallyPart.nsuite))
            if inner:
                chunks.append(kind_name + '<\n' + '\n'.join(inner) + '\n>')
            else:
                chunks.append(kind_name)
        # No newline between chunks: formatFlow requires shifts non-empty on \n
        return ''.join(chunks)


_KIND_NAMES = {
    CODEBLOCK_FRAGMENT: 'CodeBlock',
    FUNCTION_FRAGMENT: 'Function',
    CLASS_FRAGMENT: 'Class',
    FOR_FRAGMENT: 'For',
    WHILE_FRAGMENT: 'While',
    IF_FRAGMENT: 'If',
    TRY_FRAGMENT: 'Try',
    WITH_FRAGMENT: 'With',
    RETURN_FRAGMENT: 'Return',
    IMPORT_FRAGMENT: 'Import',
}


class _DocstringFrag:
    """Docstring fragment for getDisplayValue().

    CML validation expects leadingCMLComments and sideCMLComments;
    flow_ast docstrings have none, so these are empty lists.
    """

    def __init__(self, text: str | None) -> None:
        self._text = text or ''
        self.leadingCMLComments: list = []
        self.sideCMLComments: list = []

    def getDisplayValue(self) -> str:
        return self._text


class _FlowBuilder(ast.NodeVisitor):
    """Builds fragment tree from AST."""

    def __init__(self, source: str):
        self.source = source
        self.control_flow = _ControlFlow(source)

    def _pos(self, node: ast.AST) -> tuple[int, int, int, int, int, int]:
        return _pos(node, self.source)

    def _make_body(self, node: ast.AST) -> _Body:
        b, e, bln, eln, bpos, epos = self._pos(node)
        return _Body(b, e, bln, eln, bpos, epos)

    def _extract_module_docstring(self, node: ast.Module) -> None:
        """Extract module docstring from first Expr(Constant(str))."""
        doc = ast.get_docstring(node)
        if doc:
            self.control_flow.docstring = _DocstringFrag(doc)

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

    def _visit_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> _FunctionFrag:
        """Build Function fragment."""
        b, e, bln, eln, bpos, epos = self._pos(node)
        frag = _FunctionFrag(b, e, bln, eln, bpos, epos)
        frag.name = _NameContent(node.name)
        for dec in node.decorator_list:
            db, de, dbln, deln, dbpos, depos = self._pos(dec)
            dec_frag = _FragmentBase(DECORATOR_FRAGMENT, db, de, dbln, deln,
                                    dbpos, depos)
            frag.decorators.append(dec_frag)
        self._visit_suite(node.body, frag.nsuite)
        return frag

    def _visit_class(self, node: ast.ClassDef) -> _ClassFrag:
        """Build Class fragment."""
        b, e, bln, eln, bpos, epos = self._pos(node)
        frag = _ClassFrag(b, e, bln, eln, bpos, epos)
        frag.name = _NameContent(node.name)
        for dec in node.decorator_list:
            db, de, dbln, deln, dbpos, depos = self._pos(dec)
            dec_frag = _FragmentBase(DECORATOR_FRAGMENT, db, de, dbln, deln,
                                    dbpos, depos)
            frag.decorators.append(dec_frag)
        self._visit_suite(node.body, frag.nsuite)
        return frag

    def _visit_for(self, node: ast.For | ast.AsyncFor) -> _ForFrag:
        """Build For fragment."""
        b, e, bln, eln, bpos, epos = self._pos(node)
        frag = _ForFrag(b, e, bln, eln, bpos, epos)
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

    def _make_elif_part(
        self,
        condition_node: ast.expr | None,
        body: list[ast.stmt],
    ) -> _ElifPart:
        """Build ElifPart from condition and body."""
        if body:
            first, last = body[0], body[-1]
            b, _, bln, _, bpos, _ = self._pos(first)
            _, e, _, eln, _, epos = self._pos(last)
        else:
            b, e, bln, eln, bpos, epos = 0, 0, 1, 1, 1, 1
        cond = self._make_body(condition_node) if condition_node else None
        if condition_node is None:
            display_value = 'else'
        elif self.source and cond:
            display_value = self.source[cond.begin:cond.end + 1].strip().rstrip(':')
        else:
            display_value = ''
        part = _ElifPart(b, e, bln, eln, bpos, epos, condition=cond,
                        display_value=display_value)
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
        while curr.orelse and len(curr.orelse) == 1 and isinstance(
                curr.orelse[0], ast.If):
            curr = curr.orelse[0]
            frag.parts.append(self._make_elif_part(curr.test, curr.body))
        # else part
        if curr.orelse:
            frag.parts.append(self._make_elif_part(None, curr.orelse))
        return frag

    def _visit_with(self, node: ast.With | ast.AsyncWith) -> _WithFrag:
        """Build With fragment."""
        b, e, bln, eln, bpos, epos = self._pos(node)
        frag = _WithFrag(b, e, bln, eln, bpos, epos)
        self._visit_suite(node.body, frag.nsuite)
        return frag

    def _visit_try(self, node: ast.Try) -> _TryFrag:
        """Build Try fragment."""
        b, e, bln, eln, bpos, epos = self._pos(node)
        frag = _TryFrag(b, e, bln, eln, bpos, epos)
        self._visit_suite(node.body, frag.nsuite)
        for handler in node.handlers:
            hb, he, hbln, heln, hbpos, hepos = self._pos(handler)
            clause = self._make_body(handler.type) if handler.type else None
            exc_part = _ExceptPart(hb, he, hbln, heln, hbpos, hepos, clause=clause)
            self._visit_suite(handler.body, exc_part.nsuite)
            frag.exceptParts.append(exc_part)
        if node.orelse:
            frag.elsePart = self._make_elif_part(None, node.orelse)
        if node.finalbody:
            frag.finallyPart = self._make_elif_part(None, node.finalbody)
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

    def _visit_import(
        self, node: ast.Import | ast.ImportFrom
    ) -> _ImportFrag:
        """Build Import fragment with display text and fromPart/whatPart."""
        b, e, bln, eln, bpos, epos = self._pos(node)
        display_value: str
        from_part: _Body | None = None
        what_part: _Body | None = None

        if isinstance(node, ast.Import):
            names = [alias.name if alias.asname is None else
                     f'{alias.name} as {alias.asname}' for alias in node.names]
            display_value = 'import ' + ', '.join(names)
            what_part = _Body(b, e, bln, eln, bpos, epos)
        else:
            module = node.module or ''
            names = []
            for alias in node.names:
                if alias.asname is None:
                    names.append(alias.name)
                else:
                    names.append(f'{alias.name} as {alias.asname}')
            what_str = ', '.join(names)
            display_value = f'from {module} import {what_str}' if module else f'import {what_str}'
            if node.module:
                mod_b, mod_e, mod_bln, mod_eln, mod_bpos, mod_epos = self._pos(node.module)
                from_part = _Body(mod_b, mod_e, mod_bln, mod_eln, mod_bpos, mod_epos)
            what_part = _Body(b, e, bln, eln, bpos, epos)

        return _ImportFrag(b, e, bln, eln, bpos, epos,
                          display_value=display_value,
                          from_part=from_part, what_part=what_part)

    def _visit_sysexit(
        self, node: ast.Expr
    ) -> _SysExitFrag | _CodeBlock | None:
        """Check for sys.exit() and build SysExit fragment if so."""
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            return None
        call = node.value
        if isinstance(call.func, ast.Attribute):
            if (isinstance(call.func.value, ast.Name) and
                    call.func.value.id == 'sys' and
                    call.func.attr == 'exit'):
                b, e, bln, eln, bpos, epos = self._pos(node)
                arg = self._make_body(call) if call.args else None
                return _SysExitFrag(b, e, bln, eln, bpos, epos, arg=arg)
        return self._visit_code_block(node)

    def _visit_code_block(self, node: ast.AST) -> _CodeBlock:
        """Build CodeBlock fragment for generic statement."""
        b, e, bln, eln, bpos, epos = self._pos(node)
        display_value = self.source[b:e + 1] if self.source and e >= b else ''
        return _CodeBlock(b, e, bln, eln, bpos, epos,
                          display_value=display_value)

    def visit(self, node: ast.AST | None) -> None:
        """Override to collect into control_flow.nsuite."""
        if node is None:
            return
        if isinstance(node, ast.Module):
            self._extract_module_docstring(node)
            for stmt in node.body:
                self.visit(stmt)
            return
        frag = self._stmt_to_fragment(node)
        if frag is not None:
            self.control_flow.nsuite.append(frag)


def _build_control_flow(source: str, filename: str) -> _ControlFlow:
    """Parse source and build ControlFlow fragment tree."""
    try:
        tree = ast.parse(source, filename, mode='exec', type_comments=True)
    except SyntaxError as exc:
        cf = _ControlFlow(source)
        # flowuiwidget expects (line, col, msg) tuples
        line = getattr(exc, 'lineno', -1)
        col = getattr(exc, 'offset', -1)
        cf.errors.append((line, col, str(exc.msg) if exc.msg else 'Syntax error'))
        return cf
    builder = _FlowBuilder(source)
    builder.visit(tree)
    return builder.control_flow


def getControlFlowFromMemory(content: str) -> _ControlFlow:
    """Build control flow from string content."""
    return _build_control_flow(content, '<string>')


def getControlFlowFromFile(fileName: str) -> _ControlFlow:
    """Build control flow from file."""
    with open(fileName, encoding='utf-8', errors='replace') as f:
        return _build_control_flow(f.read(), fileName)
