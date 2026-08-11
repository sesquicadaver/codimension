# -*- coding: utf-8 -*-
#
# codimension - Docstring prompt context (Qt-free)
# Copyright (C) 2026  Codimension Team
# The license is described in the LICENSE file at the root directory.
#

"""Build an authoritative selection + lean support context for docstring AI.

The model must document the selected fragment. Supporting context (imports,
enclosing definition) exists only so the model does not invent names or claim
missing information.
"""

from __future__ import annotations

import ast
import re
from typing import Optional

# Qt QTextCursor.selectedText() replaces newlines with U+2029.
_QT_PARAGRAPH = "\u2029"

_DEF_NAME_RE = re.compile(
    r"^\s*(?:async\s+)?def\s+(\w+)\s*\(|^\s*class\s+(\w+)\s*[:(]",
    re.MULTILINE,
)

MAX_IMPORT_LINES = 80
MAX_SUPPORT_CHARS = 8000
MAX_FULL_DEF_CHARS = 6000


def normalize_editor_selection(text: str) -> str:
    """Normalize Qt / editor selection text to plain ``\\n`` newlines."""
    if not text:
        return ""
    return text.replace(_QT_PARAGRAPH, "\n").replace("\r\n", "\n").replace("\r", "\n")


def infer_symbol_name(fragment: str, fallback: str = "") -> str:
    """Return the first ``def``/``class`` name in ``fragment``, else ``fallback``."""
    match = _DEF_NAME_RE.search(fragment or "")
    if match:
        return match.group(1) or match.group(2) or ""
    candidate = (fallback or "").strip()
    if candidate.isidentifier():
        return candidate
    return ""


def find_enclosing_symbol_name(source: str, line: int) -> str:
    """Innermost function/class name whose span covers ``line`` (1-based)."""
    if line < 1:
        return ""
    try:
        tree = ast.parse(source or "")
    except SyntaxError:
        return ""
    best: Optional[ast.AST] = None
    best_span = None
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        start = getattr(node, "lineno", None)
        end = getattr(node, "end_lineno", None) or start
        if start is None or end is None:
            continue
        if start <= line <= end:
            span = end - start
            if best is None or best_span is None or span < best_span:
                best = node
                best_span = span
    if best is None:
        return ""
    return getattr(best, "name", "") or ""


def extract_symbol_source(source: str, symbol_name: str) -> str:
    """Return the full ``def``/``class`` text (decorators included) for ``symbol_name``."""
    if not symbol_name:
        return ""
    try:
        tree = ast.parse(source or "")
    except SyntaxError:
        return ""
    target = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == symbol_name:
            target = node
            break
    if target is None:
        return ""
    lines = (source or "").splitlines(keepends=True)
    if not lines:
        return ""
    # Include decorators that precede the def/class line.
    start = target.lineno - 1
    for deco in getattr(target, "decorator_list", ()) or ():
        deco_line = getattr(deco, "lineno", None)
        if deco_line is not None and deco_line - 1 < start:
            start = deco_line - 1
    end = (getattr(target, "end_lineno", None) or target.lineno) - 1
    if start < 0 or end >= len(lines) or end < start:
        return ""
    return "".join(lines[start : end + 1]).rstrip() + "\n"


def _module_import_block(source: str) -> str:
    """Collect leading import statements (and blank/comment gaps between them)."""
    out: list[str] = []
    count = 0
    for raw in (source or "").splitlines():
        stripped = raw.strip()
        if not stripped:
            if out:
                out.append(raw)
            continue
        if stripped.startswith("#"):
            if out:
                out.append(raw)
            continue
        if stripped.startswith("from ") or stripped.startswith("import "):
            out.append(raw)
            count += 1
            if count >= MAX_IMPORT_LINES:
                break
            continue
        # Stop at first non-import top-level statement after imports started,
        # or before any code if no imports yet — but allow encoding/future.
        if stripped.startswith("from __future__") or stripped.startswith('"""') or stripped.startswith("'''"):
            if not out:
                continue
        if count:
            break
        if not stripped.startswith('"""') and not stripped.startswith("'''"):
            # Shebang / encoding already skipped by non-import break only after imports.
            if stripped.startswith("#!") or "coding" in stripped:
                continue
            break
    text = "\n".join(out).strip()
    return text


def _enclosing_class_header(source: str, symbol_name: str) -> str:
    """If ``symbol_name`` is a method, return the enclosing class signature line(s)."""
    if not symbol_name:
        return ""
    try:
        tree = ast.parse(source or "")
    except SyntaxError:
        return ""
    lines = (source or "").splitlines()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == symbol_name:
                start = node.lineno - 1
                # Class header only (until first body line).
                first_body = node.body[0].lineno - 1 if node.body else start
                header = "\n".join(lines[start:first_body]).rstrip()
                return header
    return ""


def resolve_docstring_fragment(
    source: str,
    *,
    selected_text: str = "",
    symbol_name: str = "",
    cursor_line: int = 0,
) -> tuple[str, str]:
    """Return ``(fragment, symbol_name)`` for a docstring task.

    Prefer the editor selection as the authoritative fragment. When there is
    no selection, use the full AST span of ``symbol_name`` (or the enclosing
    symbol at ``cursor_line``).
    """
    fragment = normalize_editor_selection(selected_text).strip()
    name = infer_symbol_name(fragment, symbol_name)
    if not name and cursor_line:
        name = find_enclosing_symbol_name(source, cursor_line)
    if fragment:
        if not name:
            name = find_enclosing_symbol_name(source, cursor_line) if cursor_line else ""
        return fragment, name

    if not name:
        name = find_enclosing_symbol_name(source, cursor_line) if cursor_line else ""
    if not name:
        return "", ""
    full = extract_symbol_source(source, name)
    return full.strip(), name


def build_docstring_support_context(
    source: str,
    *,
    symbol_name: str,
    selected_fragment: str,
) -> str:
    """Lean context so the model need not invent imports / enclosing shape."""
    parts: list[str] = []
    imports = _module_import_block(source)
    if imports:
        parts.append("### Module imports\n" + imports)

    full_def = extract_symbol_source(source, symbol_name) if symbol_name else ""
    frag = (selected_fragment or "").strip()
    if full_def and frag and full_def.strip() != frag:
        clipped = full_def
        if len(clipped) > MAX_FULL_DEF_CHARS:
            clipped = clipped[: MAX_FULL_DEF_CHARS - 20] + "\n...[truncated]...\n"
        parts.append("### Full enclosing definition (for names/signature only)\n" + clipped.rstrip())

    class_header = _enclosing_class_header(source, symbol_name)
    if class_header:
        parts.append("### Enclosing class header\n" + class_header)

    if not parts:
        return "(no additional module context; rely on the selected fragment)"
    text = "\n\n".join(parts)
    if len(text) > MAX_SUPPORT_CHARS:
        return text[: MAX_SUPPORT_CHARS - 20] + "\n...[truncated]...\n"
    return text


__all__ = [
    "build_docstring_support_context",
    "extract_symbol_source",
    "find_enclosing_symbol_name",
    "infer_symbol_name",
    "normalize_editor_selection",
    "resolve_docstring_fragment",
]
