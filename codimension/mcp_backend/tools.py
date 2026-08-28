# -*- coding: utf-8 -*-
#
# codimension - MCP tool handlers (R182)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Pure MCP tool handlers over headless core (R182).

No FastMCP/MCPServer imports — keeps unit tests free of the optional SDK.
"""

from __future__ import annotations

import os
from typing import Any, Optional, cast

from core.ai_context import build_ai_context
from core.cfg import build_cfg_graph_from_file
from core.symbol_index import SymbolKind
from core.taint import analyze_function_taint_from_file
from mcp_backend.serializers import cfg_graph_to_dict, symbol_to_dict, taint_report_to_dict
from mcp_backend.session import WorkspaceSession


def open_workspace(session: WorkspaceSession, path: str) -> dict[str, Any]:
    """Open ``path`` as the workspace root and index Python files."""
    return cast(dict[str, Any], session.open_workspace(path))


def list_project_files(session: WorkspaceSession) -> dict[str, Any]:
    """List indexed project file paths (relative to workspace root when possible)."""
    session.require_open()
    assert session.root is not None
    root = session.root
    rels: list[str] = []
    for path in session.file_paths:
        try:
            rels.append(os.path.relpath(path, root))
        except ValueError:
            rels.append(path)
    return {"root": root, "files": rels}


def get_symbols(
    session: WorkspaceSession,
    *,
    file: Optional[str] = None,
    kind: Optional[str] = None,
    limit: int = 500,
) -> dict[str, Any]:
    """Return symbol records, optionally filtered by file and/or kind."""
    session.require_open()
    assert session.index is not None
    records = list(session.index.symbols())
    if file is not None:
        resolved = session.resolve_under_root(file)
        records = [r for r in records if os.path.realpath(r.file) == resolved or r.file == file]
    if kind is not None:
        want = SymbolKind(kind)
        records = [r for r in records if r.kind is want]
    capped = max(1, min(int(limit), 5000))
    out = records[:capped]
    return {
        "count": len(out),
        "truncated": len(records) > capped,
        "symbols": [symbol_to_dict(r) for r in out],
    }


def lookup_symbol(
    session: WorkspaceSession,
    name: str,
    *,
    file: Optional[str] = None,
    kind: Optional[str] = None,
    qualname: Optional[str] = None,
) -> dict[str, Any]:
    """Find definitions and references for ``name``."""
    session.require_open()
    assert session.index is not None
    kind_enum = SymbolKind(kind) if kind is not None else None
    file_filter = file
    if file is not None:
        try:
            file_filter = session.resolve_under_root(file)
        except (PermissionError, RuntimeError):
            file_filter = file
    definitions = session.index.find_definitions(name, file=file_filter, kind=kind_enum, qualname=qualname)
    if not definitions and file_filter != file:
        definitions = session.index.find_definitions(name, file=file, kind=kind_enum, qualname=qualname)
    references = session.index.find_references(name, file=file_filter)
    if not references and file_filter != file:
        references = session.index.find_references(name, file=file)
    return {
        "name": name,
        "definitions": [symbol_to_dict(r) for r in definitions],
        "references": [symbol_to_dict(r) for r in references],
    }


def get_cfg(session: WorkspaceSession, path: str) -> dict[str, Any]:
    """Build a CFG for ``path`` under the open workspace."""
    session.require_open()
    resolved = session.resolve_under_root(path)
    if not os.path.isfile(resolved):
        raise FileNotFoundError(f"file not found: {resolved}")
    graph = build_cfg_graph_from_file(resolved)
    payload = cfg_graph_to_dict(graph)
    payload["file"] = resolved
    return cast(dict[str, Any], payload)


def explain_symbol(
    session: WorkspaceSession,
    name: str,
    *,
    file: Optional[str] = None,
    kind: Optional[str] = None,
    qualname: Optional[str] = None,
) -> dict[str, Any]:
    """Build an AI context pack for ``name`` (offline; no network)."""
    session.require_open()
    assert session.index is not None
    kind_enum = SymbolKind(kind) if kind is not None else None
    pack = build_ai_context(
        session.index,
        name,
        session.sources,
        file=file,
        kind=kind_enum,
        qualname=qualname,
    )
    return cast(dict[str, Any], pack.to_dict())


def analyze_taint(
    session: WorkspaceSession,
    path: str,
    *,
    function: Optional[str] = None,
) -> dict[str, Any]:
    """Run function-local taint analysis on ``path`` (heuristic MVP)."""
    session.require_open()
    resolved = session.resolve_under_root(path)
    if not os.path.isfile(resolved):
        raise FileNotFoundError(f"file not found: {resolved}")
    report = analyze_function_taint_from_file(resolved, function=function)
    payload = taint_report_to_dict(report)
    payload["file"] = resolved
    return cast(dict[str, Any], payload)


__all__ = [
    "analyze_taint",
    "explain_symbol",
    "get_cfg",
    "get_symbols",
    "list_project_files",
    "lookup_symbol",
    "open_workspace",
]
