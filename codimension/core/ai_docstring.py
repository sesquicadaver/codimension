# -*- coding: utf-8 -*-
#
# codimension - Google docstring apply helper (Qt-free)
# Copyright (C) 2026  Codimension Team
# The license is described in the LICENSE file at the root directory.
#

"""Insert or replace a Google-style docstring on a function/class in source.

R218: apply targets a versioned symbol identity (file, document version,
qualname, source span, fingerprint) and rejects patches that fail ``ast.parse``.
"""

from __future__ import annotations

import ast
import hashlib
import zlib
from dataclasses import dataclass
from typing import Optional, Sequence, Union

DefNode = Union[ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef]


@dataclass(frozen=True)
class DocstringTarget:
    """Versioned identity of the symbol that a docstring result must apply to.

    Contract (audit P1-13 / R218)::

        file URI / path
        document version
        qualname
        source span
        symbol fingerprint
    """

    file_path: str
    symbol_name: str
    qualname: str
    document_version: int
    lineno: int
    end_lineno: int
    fingerprint: str
    col_offset: int = 0
    end_col_offset: int = -1


def document_version_of(source: str) -> int:
    """Stable CRC-32 of UTF-8 source (unsigned 32-bit) for stale-buffer checks."""
    return zlib.crc32((source or "").encode("utf-8")) & 0xFFFFFFFF


def _symbol_slice(source: str, lineno: int, end_lineno: int) -> str:
    lines = (source or "").splitlines(keepends=True)
    if lineno < 1 or end_lineno < lineno:
        return ""
    start = lineno - 1
    end = min(end_lineno, len(lines))
    if start >= len(lines):
        return ""
    return "".join(lines[start:end])


def symbol_fingerprint(source: str, lineno: int, end_lineno: int) -> str:
    """SHA-256 hex of the source lines covering ``[lineno, end_lineno]``."""
    payload = _symbol_slice(source, lineno, end_lineno).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _end_lineno(node: ast.AST) -> int:
    end = getattr(node, "end_lineno", None)
    if isinstance(end, int) and end >= 1:
        return end
    return int(getattr(node, "lineno", 1) or 1)


def _iter_qualified_defs(
    nodes: Sequence[ast.AST],
    prefix: str = "",
) -> list[tuple[str, DefNode]]:
    """Depth-first ``(qualname, node)`` for nested functions/classes."""
    out: list[tuple[str, DefNode]] = []
    for node in nodes:
        if isinstance(node, ast.ClassDef):
            qname = f"{prefix}.{node.name}" if prefix else node.name
            out.append((qname, node))
            out.extend(_iter_qualified_defs(node.body, qname))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qname = f"{prefix}.{node.name}" if prefix else node.name
            out.append((qname, node))
            out.extend(_iter_qualified_defs(node.body, qname))
    return out


def _module_defs(tree: ast.AST) -> list[tuple[str, DefNode]]:
    body = getattr(tree, "body", None) or ()
    return _iter_qualified_defs(list(body))


def _node_to_target(
    source: str,
    qname: str,
    node: DefNode,
    *,
    file_path: str = "",
) -> DocstringTarget:
    lineno = int(node.lineno)
    end = _end_lineno(node)
    return DocstringTarget(
        file_path=file_path or "",
        symbol_name=node.name,
        qualname=qname,
        document_version=document_version_of(source),
        lineno=lineno,
        end_lineno=end,
        fingerprint=symbol_fingerprint(source, lineno, end),
        col_offset=int(getattr(node, "col_offset", 0) or 0),
        end_col_offset=int(getattr(node, "end_col_offset", -1) or -1),
    )


def build_docstring_target(
    source: str,
    *,
    file_path: str = "",
    symbol_name: str = "",
    qualname: str = "",
    cursor_line: int = 0,
) -> DocstringTarget:
    """Resolve a unique versioned target from source + identity hints.

    Preference order: exact ``qualname``, then span covering ``cursor_line``
    with matching leaf name, then a unique ``symbol_name`` match.
    """
    try:
        tree = ast.parse(source or "")
    except SyntaxError as exc:
        raise ValueError(f"cannot parse buffer to build docstring target: {exc}") from exc

    defs = _module_defs(tree)
    if not defs:
        raise ValueError("no function or class definitions in buffer")

    if qualname:
        matches = [(q, n) for q, n in defs if q == qualname]
        if len(matches) == 1:
            return _node_to_target(source, matches[0][0], matches[0][1], file_path=file_path)
        if not matches:
            raise ValueError(f"qualname {qualname!r} not found in buffer")
        raise ValueError(f"qualname {qualname!r} is ambiguous in buffer")

    name = (symbol_name or "").strip()
    if cursor_line > 0:
        covering = [
            (q, n) for q, n in defs if int(n.lineno) <= cursor_line <= _end_lineno(n) and (not name or n.name == name)
        ]
        if covering:
            # Innermost span wins (shortest end-start).
            covering.sort(key=lambda item: _end_lineno(item[1]) - int(item[1].lineno))
            q, n = covering[0]
            return _node_to_target(source, q, n, file_path=file_path)

    if not name:
        raise ValueError("symbol_name or qualname required to build docstring target")

    by_name = [(q, n) for q, n in defs if n.name == name]
    if not by_name:
        raise ValueError(f"symbol {name!r} not found in buffer")
    if len(by_name) > 1:
        names = ", ".join(sorted(q for q, _ in by_name))
        raise ValueError(f"symbol {name!r} is ambiguous; use qualname (candidates: {names})")
    q, n = by_name[0]
    return _node_to_target(source, q, n, file_path=file_path)


def _find_node_for_target(tree: ast.AST, target: DocstringTarget) -> DefNode:
    defs = _module_defs(tree)
    if target.qualname:
        exact = [(q, n) for q, n in defs if q == target.qualname]
        if len(exact) == 1:
            return exact[0][1]
        if not exact:
            raise ValueError(f"qualname {target.qualname!r} not found in buffer")
        raise ValueError(f"qualname {target.qualname!r} is ambiguous in buffer")

    span_hits = [
        (q, n)
        for q, n in defs
        if n.name == target.symbol_name and int(n.lineno) == target.lineno and _end_lineno(n) == target.end_lineno
    ]
    if len(span_hits) == 1:
        return span_hits[0][1]

    by_name = [(q, n) for q, n in defs if n.name == target.symbol_name]
    if not by_name:
        raise ValueError(f"symbol {target.symbol_name!r} not found in buffer")
    if len(by_name) > 1:
        names = ", ".join(sorted(q for q, _ in by_name))
        raise ValueError(f"symbol {target.symbol_name!r} is ambiguous; use qualname (candidates: {names})")
    return by_name[0][1]


def _docstring_literal(body: str) -> str:
    cleaned = (body or "").strip("\n")
    if '"""' in cleaned and "'''" in cleaned:
        raise ValueError(
            "docstring body contains both \"\"\" and ''' delimiters; cannot build a safe Python string literal"
        )
    if '"""' in cleaned and "'''" not in cleaned:
        return f"'''{cleaned}'''"
    return f'"""{cleaned}"""'


def _compute_body_indent(lines: list[str], target: DefNode, first: ast.AST) -> str:
    header = lines[target.lineno - 1]
    def_indent = header[: len(header) - len(header.lstrip())]
    first_lineno = getattr(first, "lineno", None)
    if first_lineno == target.lineno:
        return def_indent + "    "
    if isinstance(first_lineno, int) and first_lineno >= 1:
        raw = lines[first_lineno - 1]
        return raw[: len(raw) - len(raw.lstrip())] or (def_indent + "    ")
    return def_indent + "    "


def _expand_same_line_suite(
    lines: list[str],
    target: DefNode,
    first: ast.AST,
    doc_lines: list[str],
) -> str:
    """Rewrite ``def f(): pass`` into a multi-line body with a docstring."""
    idx = target.lineno - 1
    line = lines[idx]
    col = getattr(first, "col_offset", None)
    if not isinstance(col, int) or col < 0 or col > len(line):
        colon = line.rfind(":")
        if colon < 0:
            raise ValueError("cannot locate same-line suite for docstring insert")
        col = colon + 1
        while col < len(line) and line[col].isspace():
            col += 1
    before = line[:col].rstrip()
    if not before.endswith(":"):
        if ":" not in before:
            raise ValueError("same-line suite rewrite requires a ':' in the header")
        before = before[: before.rfind(":") + 1]
    after = line[col:].lstrip()
    if after.endswith("\n"):
        after_body = after
    elif after:
        after_body = after + "\n"
    else:
        after_body = "pass\n"
    header_indent = line[: len(line) - len(line.lstrip())]
    body_indent = header_indent + "    "
    suite = body_indent + after_body.lstrip()
    if not suite.endswith("\n"):
        suite += "\n"
    rebuilt = [before + "\n"] + doc_lines + [suite]
    return "".join(lines[:idx] + rebuilt + lines[idx + 1 :])


def _validate_python(source: str) -> None:
    try:
        ast.parse(source)
    except SyntaxError as exc:
        raise ValueError(f"docstring apply produced invalid Python: {exc}") from exc


def apply_google_docstring(
    source: str,
    symbol_name: str = "",
    docstring_body: str = "",
    *,
    target: Optional[DocstringTarget] = None,
    require_version_match: bool = True,
) -> str:
    """Return ``source`` with a Google docstring applied to the target symbol.

    When ``target`` is provided (R218), the current buffer must match
    ``document_version`` and the symbol ``fingerprint`` (unless
    ``require_version_match`` is False). Ambiguous bare names without a
    ``DocstringTarget`` raise ``ValueError``.

    Always re-parses the patched source before returning.
    """
    if docstring_body is None:
        docstring_body = ""
    if target is None:
        if not symbol_name:
            raise ValueError("symbol_name or target required to apply docstring")
        target = build_docstring_target(source, symbol_name=symbol_name)
    elif symbol_name and symbol_name != target.symbol_name and symbol_name != target.qualname:
        raise ValueError(f"symbol_name {symbol_name!r} does not match target {target.qualname or target.symbol_name!r}")

    if require_version_match:
        current_ver = document_version_of(source)
        if current_ver != target.document_version:
            raise ValueError(
                "document changed since the docstring was generated "
                f"(expected version {target.document_version}, got {current_ver}); "
                "regenerate before apply"
            )
        current_fp = symbol_fingerprint(source, target.lineno, target.end_lineno)
        if current_fp != target.fingerprint:
            raise ValueError(
                f"symbol {target.qualname or target.symbol_name!r} changed since "
                "the docstring was generated; regenerate before apply"
            )

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ValueError(f"cannot parse buffer to apply docstring: {exc}") from exc

    node = _find_node_for_target(tree, target)
    lines = source.splitlines(keepends=True)
    if not lines:
        raise ValueError("empty buffer")

    body = node.body
    if not body:
        raise ValueError(f"symbol {target.qualname or target.symbol_name!r} has an empty body")

    first = body[0]
    indent = _compute_body_indent(lines, node, first)
    literal = _docstring_literal(docstring_body)
    doc_lines = [indent + part + "\n" for part in literal.splitlines()] or [
        indent + '"""\n',
        indent + '"""\n',
    ]

    existing = None
    if isinstance(first, ast.Expr):
        value = getattr(first, "value", None)
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            existing = first

    if existing is not None:
        start = existing.lineno - 1
        end = (existing.end_lineno or existing.lineno) - 1
        if existing.lineno == node.lineno:
            new_source = _expand_same_line_suite(lines, node, first, doc_lines)
        else:
            new_lines = lines[:start] + doc_lines
            if end + 1 < len(lines):
                new_lines.extend(lines[end + 1 :])
            new_source = "".join(new_lines)
    elif getattr(first, "lineno", None) == node.lineno:
        new_source = _expand_same_line_suite(lines, node, first, doc_lines)
    else:
        insert_at = first.lineno - 1
        new_source = "".join(lines[:insert_at] + doc_lines + lines[insert_at:])

    _validate_python(new_source)
    return new_source


__all__ = [
    "DocstringTarget",
    "apply_google_docstring",
    "build_docstring_target",
    "document_version_of",
    "symbol_fingerprint",
]
