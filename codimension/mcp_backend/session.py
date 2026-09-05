# -*- coding: utf-8 -*-
#
# codimension - MCP workspace session (R182 / R214)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""In-process workspace state for MCP tool handlers (R182 / R214)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional

from core.symbol_index import SymbolIndex
from mcp_backend.policy import (
    ResourceBudgetError,
    WorkspacePolicy,
    WorkspacePolicyError,
    depth_under_root,
    resolve_under_allowed_root,
)
from utils.project_scan import scan_project_files
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
        return self.policy.allowed_root

    def clear(self) -> None:
        """Drop the open workspace (policy / allowed root stay fixed)."""
        self.root = None
        self.index = None
        self.sources.clear()
        self.file_paths = ()

    def open_workspace(self, project_dir: str) -> dict[str, Any]:
        """Scan ``project_dir`` under the allowed root with resource budgets."""
        root = resolve_under_allowed_root(self.policy.allowed_root, project_dir)
        if not os.path.isdir(root):
            raise FileNotFoundError(f"workspace directory not found: {root}")

        scanned = scan_project_files(root)
        py_files = sorted(p for p in scanned if not p.endswith(os.sep) and p.endswith(".py") and os.path.isfile(p))

        sources: dict[str, str] = {}
        total_bytes = 0
        max_files = self.policy.max_files
        max_bytes = self.policy.max_bytes
        max_depth = self.policy.max_depth
        for path in py_files:
            try:
                resolve_under_allowed_root(self.policy.allowed_root, path)
            except WorkspacePolicyError:
                continue
            if max_depth > 0 and depth_under_root(root, path) > max_depth:
                continue
            try:
                with open(path, encoding="utf-8") as handle:
                    text = handle.read()
            except OSError:
                continue
            encoded = len(text.encode("utf-8"))
            if max_files > 0 and len(sources) + 1 > max_files:
                raise ResourceBudgetError(f"workspace exceeds max_files={max_files} (CDM_MCP_MAX_FILES)")
            if max_bytes > 0 and total_bytes + encoded > max_bytes:
                raise ResourceBudgetError(f"workspace exceeds max_bytes={max_bytes} (CDM_MCP_MAX_BYTES)")
            sources[path] = text
            total_bytes += encoded

        index = build_symbol_index(list(sources.keys()))
        self.root = root
        self.index = index
        self.sources = sources
        self.file_paths = tuple(sources.keys())
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
        return resolve_under_allowed_root(self.policy.allowed_root, under_open)


__all__ = ["WorkspaceSession"]
