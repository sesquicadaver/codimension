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


class ScanCancelled(Exception):
    """Raised when ``should_cancel`` returns true during a project scan (B03)."""


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
) -> set[str]:
    """Scan ``project_dir`` into a set of absolute file/dir paths (dirs end with sep).

    - Basename filters apply to entry names only (legacy Settings filters).
    - ``exclude_absolute_paths`` are path-aware (T050).
    - Symlink cycles / out-of-tree links are bounded via visited realpaths (T051).
    - ``should_cancel`` is checked cooperatively during the walk (audit B03);
      raises :class:`ScanCancelled` when it returns true.
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

    def _exclude_name(name: str) -> bool:
        if should_exclude is not None:
            return should_exclude(name)
        return should_exclude_basename(name, filters)

    def _check_cancel() -> None:
        if should_cancel is not None and should_cancel():
            raise ScanCancelled("project scan cancelled")

    def _walk(path: str) -> None:
        _check_cancel()
        try:
            entries = os.listdir(path)
        except OSError:
            return
        for item in entries:
            _check_cancel()
            if _exclude_name(item):
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
