# -*- coding: utf-8 -*-
#
# codimension - slow project-scan ignore prompt helpers
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Helpers for the slow-scan directory ignore prompt (no size heuristics)."""

from __future__ import annotations

import os
import time
from collections.abc import Iterable, Sequence
from os.path import isabs, realpath, relpath, sep

# Wall-clock threshold before offering ignore for the hot directory.
SLOW_SCAN_PROMPT_MS = 30_000


def project_relative_dir(project_dir: str, absolute_dir: str) -> str | None:
    """Return a project-relative directory path, or ``None`` for the project root.

    The result uses ``/`` separators without a trailing slash (``.cdm3`` style).
    """
    root = realpath(project_dir)
    if not root.endswith(sep):
        root_sep = root + sep
    else:
        root_sep = root
        root = root.rstrip(sep)
    cand = realpath(absolute_dir)
    if cand == root:
        return None
    if not (cand + sep).startswith(root_sep) and not cand.startswith(root_sep):
        return None
    relative = relpath(cand, root)
    if relative in (".", os.curdir):
        return None
    return relative.replace("\\", "/")


def merge_unique_paths(existing: Sequence[str], additions: Sequence[str]) -> list[str]:
    """Append new relative/absolute path strings without duplicates (order preserved)."""
    result: list[str] = []
    known: set[str] = set()
    for item in list(existing) + list(additions):
        text = str(item).strip()
        if not text or text in known:
            continue
        known.add(text)
        result.append(text)
    return result


def merge_prompt_seen(existing: Sequence[str], offered: Sequence[str]) -> list[str]:
    """Union of previously seen names and names offered in the latest prompt."""
    return merge_unique_paths(existing, offered)


def is_prompt_seen(path: str, seen: Iterable[str]) -> bool:
    """True if ``path`` was already offered in a slow-scan prompt."""
    text = str(path).strip()
    if not text:
        return True
    return text in {str(item).strip() for item in seen if str(item).strip()}


class ScanDirectoryTracker:
    """Accumulate wall time per directory while it is the active walk target.

    The directory with the largest dwell time (excluding the project root) is
    treated as the hot path that is delaying the scan.
    """

    def __init__(self, project_dir: str) -> None:
        self._root = realpath(project_dir)
        self._current = ""
        self._switched_at = time.monotonic()
        self._dwell_s: dict[str, float] = {}

    def note(self, absolute_dir: str) -> None:
        """Record that the walk entered ``absolute_dir``."""
        now = time.monotonic()
        if self._current:
            self._dwell_s[self._current] = self._dwell_s.get(self._current, 0.0) + (now - self._switched_at)
        self._current = absolute_dir
        self._switched_at = now

    def current_path(self) -> str:
        """Absolute directory currently being walked (may be empty)."""
        return self._current

    def hot_directory(self) -> str | None:
        """Absolute path of the hottest non-root directory, or ``None``."""
        now = time.monotonic()
        dwell = dict(self._dwell_s)
        if self._current:
            dwell[self._current] = dwell.get(self._current, 0.0) + (now - self._switched_at)
        root = self._root
        root_sep = root if root.endswith(sep) else root + sep
        best_path = ""
        best_s = -1.0
        for path, seconds in dwell.items():
            cand = realpath(path)
            if cand == root or cand + sep == root_sep:
                continue
            if seconds > best_s or (seconds == best_s and len(cand) > len(best_path)):
                best_s = seconds
                best_path = path if path.endswith(sep) else path + sep
        return best_path or None


def normalize_exclude_path(project_dir: str, path: str) -> str:
    """Prefer project-relative form for persistence when ``path`` is under the project."""
    text = path.strip()
    if not text:
        return text
    if isabs(text):
        relative = project_relative_dir(project_dir, text)
        return relative if relative is not None else realpath(text)
    return text.replace("\\", "/")
