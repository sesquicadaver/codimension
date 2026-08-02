#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T072: fail if remediation modules use legacy top-level utils./ui./parsers. imports.

Allowed exception: a banned import may appear only as a *direct* statement in an
``except ImportError:`` handler body (conformance harness loads brief/flow standalone).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [
    ROOT / "codimension" / "utils" / "project_scan.py",
    ROOT / "codimension" / "utils" / "atomic_io.py",
    ROOT / "codimension" / "utils" / "project_schema.py",
    ROOT / "codimension" / "parsers" / "source_spans.py",
    ROOT / "codimension" / "parsers" / "comment_binder.py",
    ROOT / "codimension" / "parsers" / "brief_ast.py",
    ROOT / "codimension" / "parsers" / "flow_ast.py",
]

BANNED_ROOTS = frozenset(
    {"utils", "ui", "parsers", "editor", "flowui", "diagram", "search", "debugger"}
)


def _roots_from_import(node: ast.AST) -> list[str]:
    """Return all top-level module roots referenced by an import node."""
    roots: list[str] = []
    if isinstance(node, ast.Import):
        for alias in node.names:
            roots.append(alias.name.split(".", 1)[0])
    elif isinstance(node, ast.ImportFrom):
        if node.level and node.level > 0:
            return []
        if node.module:
            roots.append(node.module.split(".", 1)[0])
    return roots


def _is_importerror_handler(handler: ast.ExceptHandler) -> bool:
    typ = handler.type
    if isinstance(typ, ast.Name):
        return typ.id == "ImportError"
    if isinstance(typ, ast.Tuple):
        return any(isinstance(elt, ast.Name) and elt.id == "ImportError" for elt in typ.elts)
    return False


def _allowed_fallback_ids(tree: ast.AST) -> set[int]:
    """Object ids of Import/ImportFrom nodes that are direct except-ImportError body stmts."""
    allowed: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if not _is_importerror_handler(node):
            continue
        for stmt in node.body:
            if isinstance(stmt, (ast.Import, ast.ImportFrom)):
                allowed.add(id(stmt))
    return allowed


def check_file(path: Path) -> list[str]:
    """Return human-readable failure lines for one file."""
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        return [f"{path.relative_to(ROOT)}: syntax error: {exc}"]
    allowed = _allowed_fallback_ids(tree)
    failures: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        for root in _roots_from_import(node):
            if root not in BANNED_ROOTS:
                continue
            if id(node) in allowed:
                continue
            try:
                loc = path.relative_to(ROOT)
            except ValueError:
                loc = path
            failures.append(f"{loc}:{node.lineno}: banned import of {root!r}")
    return failures


def main() -> int:
    """Return 0 if clean, 1 if banned imports found."""
    failures: list[str] = []
    for path in TARGETS:
        if not path.is_file():
            try:
                rel = path.relative_to(ROOT)
            except ValueError:
                rel = path
            failures.append(f"missing target: {rel}")
            continue
        failures.extend(check_file(path))
    if failures:
        print("T072 package-relative import gate FAILED:")
        for item in failures:
            print(f"  {item}")
        return 1
    print(f"T072 OK: {len(TARGETS)} modules use package-relative imports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
