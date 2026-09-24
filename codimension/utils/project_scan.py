# -*- coding: utf-8 -*-
#
# codimension - project filesystem scan (headless)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Headless project tree scan with path-aware excludes and symlink bounds (T050–T051)."""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterable, Sequence
from os.path import isdir, islink, realpath, sep

# Packaging / tool output that mirrors the source tree (setuptools ``build/lib``,
# wheel ``dist``, coverage HTML, etc.). Skipping these prevents import-diagram
# and analysis from treating every module as two ModuleOfInterest nodes (R277).
_TOP_LEVEL_ARTIFACT_DIRS = frozenset({"build", "dist", "htmlcov", ".eggs"})
_ANY_LEVEL_ARTIFACT_DIRS = frozenset(
    {
        "__pycache__",
        ".tox",
        ".nox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".svn",
        ".cvs",
        ".git",
        ".hg",
    }
)
_ARTIFACT_DIR_SUFFIXES = (".egg-info",)


class ScanCancelled(Exception):
    """Raised when ``should_cancel`` returns true during a project scan (B03)."""


def is_packaging_artifact_basename(name: str, *, at_project_root: bool = False) -> bool:
    """True if a directory/file basename is a known packaging or tool artifact.

    ``build`` / ``dist`` / ``htmlcov`` / ``.eggs`` are only treated as artifacts
    at the project root so a legitimate nested package named ``build`` is kept.
    """
    if not name:
        return False
    if name in _ANY_LEVEL_ARTIFACT_DIRS:
        return True
    if name.endswith(_ARTIFACT_DIR_SUFFIXES):
        return True
    if at_project_root and name in _TOP_LEVEL_ARTIFACT_DIRS:
        return True
    return False


def path_has_packaging_artifact(path: str, project_dir: str | None = None) -> bool:
    """True if ``path`` lies under a packaging artifact directory.

    When ``project_dir`` is set, top-level-only names (``build``, ``dist``, …)
    match solely as direct children of that project root. Nested packages named
    ``build`` are kept. Without a project root, top-level artifact names match
    at any depth (conservative filter for absolute paths already on disk).
    """
    if not path:
        return False
    try:
        cand = realpath(path)
    except OSError:
        cand = path.replace("\\", "/")

    root = ""
    if project_dir:
        try:
            root = realpath(project_dir).rstrip(sep)
        except OSError:
            root = project_dir.replace("\\", "/").rstrip("/").rstrip("\\")

    if root and (cand == root or cand.startswith(root + sep)):
        rel = cand[len(root) :].lstrip(sep)
        parts = [p for p in rel.split(sep) if p]
        if not parts:
            return False
        if is_packaging_artifact_basename(parts[0], at_project_root=True):
            return True
        return any(is_packaging_artifact_basename(p, at_project_root=False) for p in parts[1:])

    parts = [p for p in cand.split(sep) if p]
    return any(is_packaging_artifact_basename(p, at_project_root=True) for p in parts)


def path_is_under_or_equal(candidate: str, root: str) -> bool:
    """True if ``candidate`` is ``root`` or a path under it (realpath, sep-normalized)."""
    cand = realpath(candidate)
    base = realpath(root)
    if not base.endswith(sep):
        base_prefix = base + sep
    else:
        base_prefix = base
        base = base.rstrip(sep)
    if cand == base:
        return True
    if not cand.endswith(sep):
        cand_check = cand
    else:
        cand_check = cand.rstrip(sep)
    return cand_check.startswith(base_prefix) or (cand_check + sep).startswith(base_prefix)


def is_excluded_by_absolute_paths(candidate: str, exclude_paths: Sequence[str]) -> bool:
    """Path-aware exclusion: match exact path or descendants (not basename-only)."""
    if not exclude_paths:
        return False
    cand_real = realpath(candidate)
    for excl in exclude_paths:
        excl_real = realpath(excl)
        if cand_real == excl_real:
            return True
        excl_prefix = excl_real.rstrip(sep) + sep
        if cand_real.startswith(excl_prefix):
            return True
    return False


def compile_basename_filters(patterns: Iterable[str]) -> list[re.Pattern[str]]:
    """Compile basename regex filters (Settings projectFilesFilters)."""
    return [re.compile(flt) for flt in patterns]


def should_exclude_basename(name: str, filters: Sequence[re.Pattern[str]]) -> bool:
    """True if basename matches a Settings-style filter (``.pylintrc`` never excluded)."""
    if name == ".pylintrc":
        return False
    for excl in filters:
        if excl.match(name):
            return True
    return False


def scan_project_files(
    project_dir: str,
    *,
    basename_filters: Sequence[re.Pattern[str]] | None = None,
    exclude_absolute_paths: Sequence[str] | None = None,
    venv_dir: str | None = None,
    should_exclude: Callable[[str], bool] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    on_directory: Callable[[str], None] | None = None,
) -> set[str]:
    """Scan ``project_dir`` into a set of absolute file/dir paths (dirs end with sep).

    - Basename filters apply to entry names only (legacy Settings filters).
    - Packaging artifact dirs (``build``, ``dist``, ``*.egg-info``, …) are
      skipped unconditionally (R277) so mirrored setuptools trees do not
      duplicate every module in analysis / import diagrams.
    - ``exclude_absolute_paths`` are path-aware (T050).
    - Symlink cycles / out-of-tree links are bounded via visited realpaths (T051).
    - ``should_cancel`` is checked cooperatively during the walk (audit B03);
      raises :class:`ScanCancelled` when it returns true.
    - ``on_directory`` is invoked with the absolute dir path (trailing sep) when
      the walk enters that directory — used for slow-scan progress prompts.
    """
    root = realpath(project_dir)
    if not root.endswith(sep):
        root_sep = root + sep
    else:
        root_sep = root
        root = root.rstrip(sep)

    filters = list(basename_filters or [])
    exclude_paths = [realpath(p) for p in (exclude_absolute_paths or [])]
    if venv_dir:
        venv_real = realpath(venv_dir)
        if venv_real not in exclude_paths:
            exclude_paths.append(venv_real)

    files: set[str] = {root_sep}
    visited: set[str] = {root}

    def _exclude_name(name: str, *, at_project_root: bool) -> bool:
        if is_packaging_artifact_basename(name, at_project_root=at_project_root):
            return True
        if should_exclude is not None:
            return should_exclude(name)
        return should_exclude_basename(name, filters)

    def _check_cancel() -> None:
        if should_cancel is not None and should_cancel():
            raise ScanCancelled("project scan cancelled")

    def _walk(path: str) -> None:
        _check_cancel()
        if on_directory is not None:
            on_directory(path)
        try:
            entries = os.listdir(path)
        except OSError:
            return
        at_root = path == root_sep
        for item in entries:
            _check_cancel()
            if _exclude_name(item, at_project_root=at_root):
                continue
            candidate = path + item
            try:
                cand_real = realpath(candidate)
            except OSError:
                continue

            if is_excluded_by_absolute_paths(cand_real, exclude_paths):
                continue

            # Bound traversal to project tree + visited set (T051)
            if cand_real in visited:
                continue
            if not path_is_under_or_equal(cand_real, root):
                # Out-of-tree symlink target — do not follow
                continue

            is_dir = isdir(candidate)
            if is_dir:
                visited.add(cand_real)
                files.add(candidate if candidate.endswith(sep) else candidate + sep)
                _walk(candidate if candidate.endswith(sep) else candidate + sep)
            else:
                # File (or symlink-to-file within tree)
                if islink(candidate):
                    visited.add(cand_real)
                files.add(candidate)

    _walk(root_sep)
    _check_cancel()
    return files
