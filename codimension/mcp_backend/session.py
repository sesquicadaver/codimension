# -*- coding: utf-8 -*-
#
# codimension - MCP workspace session (R182 / R214 / R223)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""In-process workspace state for MCP tool handlers (R182 / R214 / R223)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional, cast

from core.symbol_index import SymbolIndex
from mcp_backend.policy import (
    WorkspacePolicy,
    resolve_under_allowed_root,
)
from mcp_backend.walker import walk_workspace_sources
from utils.symbol_index_brief import build_symbol_index


@dataclass
class WorkspaceSession:
    """Mutable workspace bound to one MCP process.

    Holds an absolute project root (must stay under the immutable
    :class:`WorkspacePolicy.allowed_root`), indexed symbols, and per-file
    source text for CFG / AI-context / taint tools. Qt-free.
    """

    policy: WorkspacePolicy
    root: Optional[str] = None
    index: Optional[SymbolIndex] = None
    sources: dict[str, str] = field(default_factory=dict)
    file_paths: tuple[str, ...] = ()

    @property
    def allowed_root(self) -> str:
        """Immutable filesystem authority for this MCP process."""
        return str(self.policy.allowed_root)

    def clear(self) -> None:
        """Drop the open workspace (policy / allowed root stay fixed)."""
        self.root = None
        self.index = None
        self.sources.clear()
        self.file_paths = ()

    def open_workspace(self, project_dir: str) -> dict[str, Any]:
        """Scan ``project_dir`` under the allowed root with in-walk resource budgets (R223)."""
        root = resolve_under_allowed_root(self.policy.allowed_root, project_dir)
        if not os.path.isdir(root):
            raise FileNotFoundError(f"workspace directory not found: {root}")

        walked = walk_workspace_sources(root, self.policy, allowed_root=self.policy.allowed_root)
        sources = walked.sources
        total_bytes = walked.bytes_loaded
        max_files = self.policy.max_files
        max_bytes = self.policy.max_bytes
        max_depth = self.policy.max_depth

        index = build_symbol_index(list(sources.keys()))
        self.root = root
        self.index = index
        self.sources = sources
        self.file_paths = tuple(sorted(sources.keys()))
        return {
            "root": root,
            "allowed_root": self.policy.allowed_root,
            "file_count": len(self.file_paths),
            "symbol_count": len(index),
            "bytes_loaded": total_bytes,
            "max_files": max_files,
            "max_bytes": max_bytes,
            "max_depth": max_depth,
        }

    def require_open(self) -> None:
        """Raise ``RuntimeError`` when no workspace is open."""
        if not self.root or self.index is None:
            raise RuntimeError("no workspace open; call open_workspace first")

    def resolve_under_root(self, path: str) -> str:
        """Resolve ``path`` under the open root; reject escapes."""
        self.require_open()
        assert self.root is not None
        # Open root is already under allowed_root; also reject escapes from both.
        under_open = resolve_under_allowed_root(self.root, path)
        resolved = resolve_under_allowed_root(self.policy.allowed_root, under_open)
        return cast(str, resolved)


__all__ = ["WorkspaceSession"]
