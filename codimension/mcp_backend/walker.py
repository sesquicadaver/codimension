# -*- coding: utf-8 -*-
#
# codimension - MCP budget-aware workspace walker (R223)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Budget-aware directory walk for MCP ``open_workspace`` (R223).

Unlike :func:`utils.project_scan.scan_project_files`, this walker applies
depth / file-count / byte budgets *during* traversal: it does not materialize
the full path set first, and it reads ``.py`` sources in bounded chunks so a
single oversized file cannot be fully loaded before the byte limit fires.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from os.path import isdir, islink, realpath, sep
from typing import Optional

from mcp_backend.policy import (
    ResourceBudgetError,
    WorkspacePolicy,
    WorkspacePolicyError,
    depth_under_root,
    resolve_under_allowed_root,
)
from utils.project_scan import path_is_under_or_equal

#: Chunk size for budgeted source reads (bytes).
_READ_CHUNK_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class WorkspaceWalkResult:
    """Sources loaded under budget plus aggregate byte count."""

    sources: dict[str, str]
    bytes_loaded: int


def _read_py_budgeted(path: str, *, remaining_bytes: Optional[int]) -> tuple[str, int]:
    """Read UTF-8 source in chunks; stop when ``remaining_bytes`` would be exceeded.

    ``remaining_bytes`` is ``None`` when the byte budget is unlimited (``max_bytes == 0``).
    """
    chunks: list[bytes] = []
    total = 0
    with open(path, "rb") as handle:
        while True:
            piece = handle.read(_READ_CHUNK_BYTES)
            if not piece:
                break
            total += len(piece)
            if remaining_bytes is not None and total > remaining_bytes:
                raise ResourceBudgetError(
                    f"workspace exceeds max_bytes budget while reading {path} (CDM_MCP_MAX_BYTES)"
                )
            chunks.append(piece)
    data = b"".join(chunks)
    try:
        return data.decode("utf-8"), len(data)
    except UnicodeDecodeError as exc:
        raise OSError(f"not UTF-8 source: {path}") from exc


def walk_workspace_sources(
    root: str,
    policy: WorkspacePolicy,
    *,
    allowed_root: Optional[str] = None,
) -> WorkspaceWalkResult:
    """Walk ``root`` and load ``.py`` files under :class:`WorkspacePolicy` budgets.

    Depth overruns skip the entry (and prune directory descent). File-count and
    byte overruns raise :class:`ResourceBudgetError` immediately.
    """
    root_real = realpath(root)
    if not root_real.endswith(sep):
        root_sep = root_real + sep
    else:
        root_sep = root_real
        root_real = root_real.rstrip(sep)

    authority = realpath(allowed_root or policy.allowed_root)
    max_files = policy.max_files
    max_bytes = policy.max_bytes
    max_depth = policy.max_depth

    sources: dict[str, str] = {}
    total_bytes = 0
    visited: set[str] = {root_real}

    def _remaining() -> Optional[int]:
        if max_bytes <= 0:
            return None
        return max_bytes - total_bytes

    def _walk(dir_path: str) -> None:
        nonlocal total_bytes
        try:
            entries = os.listdir(dir_path)
        except OSError:
            return
        for item in entries:
            candidate = dir_path + item if dir_path.endswith(sep) else dir_path + sep + item
            try:
                st = os.lstat(candidate)
            except OSError:
                continue

            try:
                cand_real = realpath(candidate)
            except OSError:
                continue

            try:
                resolve_under_allowed_root(authority, cand_real)
            except WorkspacePolicyError:
                continue

            if cand_real in visited:
                continue
            if not path_is_under_or_equal(cand_real, root_real):
                continue

            # Directory (including in-tree symlink-to-dir).
            if isdir(candidate):
                if islink(candidate) and (cand_real in visited or not path_is_under_or_equal(cand_real, root_real)):
                    continue
                try:
                    depth = depth_under_root(root_real, cand_real)
                except WorkspacePolicyError:
                    continue
                if max_depth > 0 and depth > max_depth:
                    continue
                # Files inside would be depth+1 — prune when at the limit.
                if max_depth > 0 and depth >= max_depth:
                    continue
                visited.add(cand_real)
                _walk(candidate if candidate.endswith(sep) else candidate + sep)
                continue

            # Regular file (or in-tree symlink-to-file).
            if islink(candidate):
                visited.add(cand_real)
            if not str(candidate).endswith(".py"):
                continue
            if not os.path.isfile(candidate):
                continue

            try:
                depth = depth_under_root(root_real, candidate)
            except WorkspacePolicyError:
                continue
            if max_depth > 0 and depth > max_depth:
                continue

            if max_files > 0 and len(sources) + 1 > max_files:
                raise ResourceBudgetError(f"workspace exceeds max_files={max_files} (CDM_MCP_MAX_FILES)")

            remaining = _remaining()
            declared = int(getattr(st, "st_size", 0) or 0)
            if remaining is not None and declared > remaining:
                raise ResourceBudgetError(
                    f"workspace exceeds max_bytes={max_bytes} (CDM_MCP_MAX_BYTES); "
                    f"declared size {declared} for {candidate}"
                )

            try:
                text, encoded = _read_py_budgeted(candidate, remaining_bytes=remaining)
            except OSError:
                continue

            if remaining is not None and encoded > remaining:
                raise ResourceBudgetError(f"workspace exceeds max_bytes={max_bytes} (CDM_MCP_MAX_BYTES)")

            key = cand_real if os.path.isfile(cand_real) else os.path.abspath(candidate)
            sources[key] = text
            total_bytes += encoded

    _walk(root_sep)
    return WorkspaceWalkResult(sources=sources, bytes_loaded=total_bytes)


__all__ = [
    "WorkspaceWalkResult",
    "walk_workspace_sources",
]
