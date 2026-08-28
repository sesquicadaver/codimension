# -*- coding: utf-8 -*-
#
# codimension - MCP workspace session (R182)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""In-process workspace state for MCP tool handlers (R182)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional

from core.symbol_index import SymbolIndex
from utils.project_scan import scan_project_files
from utils.symbol_index_brief import build_symbol_index


@dataclass
class WorkspaceSession:
    """Mutable workspace bound to one MCP process.

    Holds an absolute project root, indexed symbols, and per-file source text
    for CFG / AI-context / taint tools. Qt-free.
    """

    root: Optional[str] = None
    index: Optional[SymbolIndex] = None
    sources: dict[str, str] = field(default_factory=dict)
    file_paths: tuple[str, ...] = ()

    def clear(self) -> None:
        """Drop the open workspace."""
        self.root = None
        self.index = None
        self.sources.clear()
        self.file_paths = ()

    def open_workspace(self, project_dir: str) -> dict[str, Any]:
        """Scan ``project_dir``, index ``*.py`` files, and return a summary dict."""
        root = os.path.realpath(os.path.expanduser(project_dir))
        if not os.path.isdir(root):
            raise FileNotFoundError(f"workspace directory not found: {root}")

        scanned = scan_project_files(root)
        py_files = sorted(p for p in scanned if not p.endswith(os.sep) and p.endswith(".py") and os.path.isfile(p))
        sources: dict[str, str] = {}
        for path in py_files:
            try:
                with open(path, encoding="utf-8") as handle:
                    sources[path] = handle.read()
            except OSError:
                continue

        index = build_symbol_index(list(sources.keys()))
        self.root = root
        self.index = index
        self.sources = sources
        self.file_paths = tuple(sources.keys())
        return {
            "root": root,
            "file_count": len(self.file_paths),
            "symbol_count": len(index),
        }

    def require_open(self) -> None:
        """Raise ``RuntimeError`` when no workspace is open."""
        if not self.root or self.index is None:
            raise RuntimeError("no workspace open; call open_workspace first")

    def resolve_under_root(self, path: str) -> str:
        """Resolve ``path`` under the open root; reject escapes."""
        self.require_open()
        assert self.root is not None
        candidate = path if os.path.isabs(path) else os.path.join(self.root, path)
        real = os.path.realpath(candidate)
        root_sep = self.root if self.root.endswith(os.sep) else self.root + os.sep
        if real != self.root and not real.startswith(root_sep):
            raise PermissionError(f"path escapes workspace root: {path}")
        return real


__all__ = ["WorkspaceSession"]
