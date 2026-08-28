# -*- coding: utf-8 -*-
#
# codimension - MCP stdio server entry (R182)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Stdio MCP server wrapping headless tool handlers (R182).

Requires optional dependency ``mcp`` (``pip install 'codimension[mcp]'``) and a
non-empty ``CDM_MCP_TOKEN`` environment variable (fail-closed).
"""

from __future__ import annotations

import os
import sys
from typing import Any, Optional, cast

# Make ``core`` / ``utils`` / ``mcp_backend`` importable when launched via
# console_scripts (same layout bootstrap as ``codimension.codimension``).
_PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PKG_DIR not in sys.path:
    sys.path.insert(0, _PKG_DIR)

from mcp_backend import tools as tool_handlers  # noqa: E402
from mcp_backend.auth import require_startup_token_or_exit  # noqa: E402
from mcp_backend.session import WorkspaceSession  # noqa: E402


def _load_mcp_server_class() -> Any:
    """Import MCPServer from the official SDK; exit 2 when missing."""
    try:
        from mcp.server.mcpserver import MCPServer
    except ImportError as exc:  # pragma: no cover - exercised via dedicated test
        sys.stderr.write(
            "codimension-mcp: missing optional dependency 'mcp'. Install with: pip install 'codimension[mcp]'\n"
        )
        raise SystemExit(2) from exc
    return MCPServer


def build_server(session: Optional[WorkspaceSession] = None) -> Any:
    """Construct an :class:`MCPServer` bound to ``session`` (or a fresh one)."""
    MCPServer = _load_mcp_server_class()
    workspace = session if session is not None else WorkspaceSession()
    server = MCPServer("codimension")

    @server.tool()
    def open_workspace(path: str) -> dict[str, Any]:
        """Open a local project directory and index Python sources."""
        return cast(dict[str, Any], tool_handlers.open_workspace(workspace, path))

    @server.tool()
    def list_project_files() -> dict[str, Any]:
        """List indexed ``.py`` files in the open workspace."""
        return cast(dict[str, Any], tool_handlers.list_project_files(workspace))

    @server.tool()
    def get_symbols(
        file: Optional[str] = None,
        kind: Optional[str] = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        """List symbol records; optional ``file`` / ``kind`` filters."""
        return cast(
            dict[str, Any],
            tool_handlers.get_symbols(workspace, file=file, kind=kind, limit=limit),
        )

    @server.tool()
    def lookup_symbol(
        name: str,
        file: Optional[str] = None,
        kind: Optional[str] = None,
        qualname: Optional[str] = None,
    ) -> dict[str, Any]:
        """Find definitions and references for a symbol name."""
        return cast(
            dict[str, Any],
            tool_handlers.lookup_symbol(workspace, name, file=file, kind=kind, qualname=qualname),
        )

    @server.tool()
    def get_cfg(path: str) -> dict[str, Any]:
        """Build a control-flow graph for a Python file under the workspace."""
        return cast(dict[str, Any], tool_handlers.get_cfg(workspace, path))

    @server.tool()
    def explain_symbol(
        name: str,
        file: Optional[str] = None,
        kind: Optional[str] = None,
        qualname: Optional[str] = None,
    ) -> dict[str, Any]:
        """Pack offline AI context (definitions, CFG slice, excerpt) for a symbol."""
        return cast(
            dict[str, Any],
            tool_handlers.explain_symbol(workspace, name, file=file, kind=kind, qualname=qualname),
        )

    @server.tool()
    def analyze_taint(path: str, function: Optional[str] = None) -> dict[str, Any]:
        """Heuristic function-local taint analysis (not a security proof)."""
        return cast(
            dict[str, Any],
            tool_handlers.analyze_taint(workspace, path, function=function),
        )

    return server


def main() -> None:
    """Fail-closed auth, then serve MCP tools over stdio."""
    require_startup_token_or_exit()
    server = build_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()


__all__ = ["build_server", "main"]
