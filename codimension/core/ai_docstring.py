# -*- coding: utf-8 -*-
#
# codimension - Google docstring apply helper (Qt-free)
# Copyright (C) 2026  Codimension Team
# The license is described in the LICENSE file at the root directory.
#

"""Insert or replace a Google-style docstring on a function/class in source."""

from __future__ import annotations

import ast
from typing import Optional


def _find_target(tree: ast.AST, name: str) -> Optional[ast.AST]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
            return node
    return None


def _docstring_literal(body: str) -> str:
    cleaned = (body or "").strip("\n")
    if '"""' in cleaned and "'''" not in cleaned:
        return f"'''{cleaned}'''"
    return f'"""{cleaned}"""'


def apply_google_docstring(source: str, symbol_name: str, docstring_body: str) -> str:
    """Return ``source`` with a Google docstring applied to ``symbol_name``.

    Replaces an existing docstring if present; otherwise inserts one as the
    first statement in the function/class body.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ValueError(f"cannot parse buffer to apply docstring: {exc}") from exc
    target = _find_target(tree, symbol_name)
    if target is None:
        raise ValueError(f"symbol {symbol_name!r} not found in buffer")
    if not isinstance(target, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        raise ValueError(f"symbol {symbol_name!r} is not a function or class")

    lines = source.splitlines(keepends=True)
    if not lines:
        raise ValueError("empty buffer")

    # Indentation of the first body statement (or synthetic indent).
    body = target.body
    if not body:
        raise ValueError(f"symbol {symbol_name!r} has an empty body")

    first = body[0]
    indent = "    "
    if hasattr(first, "lineno") and first.lineno >= 1:
        raw = lines[first.lineno - 1]
        indent = raw[: len(raw) - len(raw.lstrip())] or "    "

    literal = _docstring_literal(docstring_body)
    doc_lines = [indent + part + "\n" for part in literal.splitlines()] or [indent + '"""\n', indent + '"""\n']

    existing = None
    if isinstance(first, ast.Expr):
        value = getattr(first, "value", None)
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            existing = first

    if existing is not None:
        start = existing.lineno - 1
        end = (existing.end_lineno or existing.lineno) - 1
        new_lines = lines[:start] + doc_lines
        if end + 1 < len(lines):
            new_lines.extend(lines[end + 1 :])
        return "".join(new_lines)

    # Insert after the def/class header line (and any decorators already included
    # before lineno). Body starts at first.lineno — insert before it.
    insert_at = first.lineno - 1
    return "".join(lines[:insert_at] + doc_lines + lines[insert_at:])


__all__ = ["apply_google_docstring"]
