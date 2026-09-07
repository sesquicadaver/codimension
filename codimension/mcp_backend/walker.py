# -*- coding: utf-8 -*-
#
# codimension - MCP budget-aware workspace walker (R223 / R238)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Budget-aware directory walk for MCP ``open_workspace`` (R223 / R238).

Unlike :func:`utils.project_scan.scan_project_files`, this walker applies
depth / file-count / byte budgets *during* traversal: it does not materialize
the full path set first, and it reads ``.py`` sources in bounded chunks so a
single oversized file cannot be fully loaded before the byte limit fires.

R238: ``os.scandir`` with deterministic name order, entry/directory budgets,
fd-relative ``openat`` + ``O_NOFOLLOW``, and ``fstat`` inode/device checks so
symlink TOCTOU cannot escape the workspace after the path was validated.
"""

from __future__ import annotations

import os
import stat as stat_mod
from dataclasses import dataclass
from os.path import realpath, sep
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

_O_RDONLY = getattr(os, "O_RDONLY", 0)
_O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


@dataclass(frozen=True, slots=True)
class WorkspaceWalkResult:
    """Sources loaded under budget plus aggregate byte count."""

    sources: dict[str, str]
    bytes_loaded: int


def _read_py_budgeted_fd(fd: int, *, remaining_bytes: Optional[int], label: str) -> tuple[str, int]:
    """Read UTF-8 source from ``fd`` in chunks; stop when the byte budget would be exceeded."""
    chunks: list[bytes] = []
    total = 0
    while True:
        piece = os.read(fd, _READ_CHUNK_BYTES)
        if not piece:
            break
        total += len(piece)
        if remaining_bytes is not None and total > remaining_bytes:
            raise ResourceBudgetError(f"workspace exceeds max_bytes budget while reading {label} (CDM_MCP_MAX_BYTES)")
        chunks.append(piece)
    data = b"".join(chunks)
    try:
        return data.decode("utf-8"), len(data)
    except UnicodeDecodeError as exc:
        raise OSError(f"not UTF-8 source: {label}") from exc


def _open_nofollow(dir_fd: int, name: str, flags: int) -> int:
    """``openat`` relative to ``dir_fd`` with ``O_NOFOLLOW`` when available."""
    return os.open(name, flags | _O_NOFOLLOW, dir_fd=dir_fd)


def walk_workspace_sources(
    root: str,
    policy: WorkspacePolicy,
    *,
    allowed_root: Optional[str] = None,
) -> WorkspaceWalkResult:
    """Walk ``root`` and load ``.py`` files under :class:`WorkspacePolicy` budgets.

    Depth overruns skip the entry (and prune directory descent). File-count,
    entry-count, directory-count, and byte overruns raise
    :class:`ResourceBudgetError` immediately. Symlinks are skipped (R238).
    """
    root_real = realpath(root)
    authority = realpath(allowed_root or policy.allowed_root)
    try:
        resolve_under_allowed_root(authority, root_real)
    except WorkspacePolicyError as exc:
        raise ResourceBudgetError(str(exc)) from exc

    max_files = policy.max_files
    max_bytes = policy.max_bytes
    max_depth = policy.max_depth
    max_entries = policy.max_entries
    max_directories = policy.max_directories

    sources: dict[str, str] = {}
    total_bytes = 0
    entries_seen = 0
    directories_opened = 0
    visited_dirs: set[tuple[int, int]] = set()

    def _remaining() -> Optional[int]:
        if max_bytes <= 0:
            return None
        return int(max_bytes) - int(total_bytes)

    def _bump_entries() -> None:
        nonlocal entries_seen
        entries_seen += 1
        if max_entries > 0 and entries_seen > max_entries:
            raise ResourceBudgetError(f"workspace exceeds max_entries={max_entries} (CDM_MCP_MAX_ENTRIES)")

    def _walk(dir_fd: int, dir_path: str) -> None:
        nonlocal total_bytes, directories_opened
        try:
            with os.scandir(dir_fd) as scanner:
                entries = sorted(scanner, key=lambda item: item.name)
        except OSError:
            return

        for entry in entries:
            _bump_entries()
            name = entry.name
            if name in (".", ".."):
                continue
            candidate = dir_path + name if dir_path.endswith(sep) else dir_path + sep + name

            try:
                if entry.is_symlink():
                    continue
            except OSError:
                continue

            try:
                is_dir = entry.is_dir(follow_symlinks=False)
                is_file = entry.is_file(follow_symlinks=False)
            except OSError:
                continue

            if is_dir:
                try:
                    depth = depth_under_root(root_real, candidate)
                except WorkspacePolicyError:
                    continue
                if max_depth > 0 and depth > max_depth:
                    continue
                if max_depth > 0 and depth >= max_depth:
                    continue

                try:
                    child_fd = _open_nofollow(dir_fd, name, _O_RDONLY | _O_DIRECTORY)
                except OSError:
                    continue
                try:
                    st = os.fstat(child_fd)
                    if not stat_mod.S_ISDIR(st.st_mode):
                        continue
                    try:
                        entry_st = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if (st.st_ino, st.st_dev) != (entry_st.st_ino, entry_st.st_dev):
                        continue
                    identity = (int(st.st_dev), int(st.st_ino))
                    if identity in visited_dirs:
                        continue
                    child_real = realpath(candidate)
                    try:
                        resolve_under_allowed_root(authority, child_real)
                    except WorkspacePolicyError:
                        continue
                    if not path_is_under_or_equal(child_real, root_real):
                        continue
                    directories_opened += 1
                    if max_directories > 0 and directories_opened > max_directories:
                        raise ResourceBudgetError(
                            f"workspace exceeds max_directories={max_directories} (CDM_MCP_MAX_DIRECTORIES)"
                        )
                    visited_dirs.add(identity)
                    child_path = candidate if candidate.endswith(sep) else candidate + sep
                    _walk(child_fd, child_path)
                finally:
                    try:
                        os.close(child_fd)
                    except OSError:
                        pass
                continue

            if not is_file or not name.endswith(".py"):
                continue

            try:
                depth = depth_under_root(root_real, candidate)
            except WorkspacePolicyError:
                continue
            if max_depth > 0 and depth > max_depth:
                continue

            if max_files > 0 and len(sources) + 1 > max_files:
                raise ResourceBudgetError(f"workspace exceeds max_files={max_files} (CDM_MCP_MAX_FILES)")

            try:
                entry_st = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            remaining = _remaining()
            declared = int(getattr(entry_st, "st_size", 0) or 0)
            if remaining is not None and declared > remaining:
                raise ResourceBudgetError(
                    f"workspace exceeds max_bytes={max_bytes} (CDM_MCP_MAX_BYTES); "
                    f"declared size {declared} for {candidate}"
                )

            try:
                file_fd = _open_nofollow(dir_fd, name, _O_RDONLY)
            except OSError:
                continue
            try:
                st = os.fstat(file_fd)
                if not stat_mod.S_ISREG(st.st_mode):
                    continue
                if (st.st_ino, st.st_dev) != (entry_st.st_ino, entry_st.st_dev):
                    continue
                file_real = realpath(candidate)
                try:
                    resolve_under_allowed_root(authority, file_real)
                except WorkspacePolicyError:
                    continue
                if not path_is_under_or_equal(file_real, root_real):
                    continue
                try:
                    text, encoded = _read_py_budgeted_fd(
                        file_fd,
                        remaining_bytes=remaining,
                        label=candidate,
                    )
                except OSError:
                    continue
            finally:
                try:
                    os.close(file_fd)
                except OSError:
                    pass

            if remaining is not None and encoded > remaining:
                raise ResourceBudgetError(f"workspace exceeds max_bytes={max_bytes} (CDM_MCP_MAX_BYTES)")

            sources[file_real] = text
            total_bytes += encoded

    root_flags = _O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW
    try:
        root_fd = os.open(root_real, root_flags)
    except OSError as exc:
        raise ResourceBudgetError(f"cannot open workspace root: {root_real}") from exc
    try:
        st = os.fstat(root_fd)
        if not stat_mod.S_ISDIR(st.st_mode):
            raise ResourceBudgetError(f"workspace root is not a directory: {root_real}")
        directories_opened += 1
        if max_directories > 0 and directories_opened > max_directories:
            raise ResourceBudgetError(f"workspace exceeds max_directories={max_directories} (CDM_MCP_MAX_DIRECTORIES)")
        visited_dirs.add((int(st.st_dev), int(st.st_ino)))
        root_path = root_real if root_real.endswith(sep) else root_real + sep
        _walk(root_fd, root_path)
    finally:
        try:
            os.close(root_fd)
        except OSError:
            pass

    return WorkspaceWalkResult(sources=sources, bytes_loaded=total_bytes)


__all__ = [
    "WorkspaceWalkResult",
    "walk_workspace_sources",
]
