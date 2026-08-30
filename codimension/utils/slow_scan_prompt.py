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
from collections.abc import Callable, Iterable, Sequence
from os.path import isdir, join, realpath, sep

# Wall-clock threshold before offering top-level ignore choices.
SLOW_SCAN_PROMPT_MS = 30_000


def list_top_level_dir_names(
    project_dir: str,
    *,
    should_exclude_name: Callable[[str], bool] | None = None,
) -> list[str]:
    """Return sorted top-level directory basenames under ``project_dir``.

    Basename filters (dot-dirs, ``__pycache__``, …) are applied when
    ``should_exclude_name`` is provided. No size / entry-count heuristics.
    """
    root = realpath(project_dir)
    if not root.endswith(sep):
        root_sep = root + sep
    else:
        root_sep = root
    try:
        entries = os.listdir(root_sep)
    except OSError:
        return []
    names: list[str] = []
    for name in entries:
        if should_exclude_name is not None and should_exclude_name(name):
            continue
        candidate = join(root_sep, name)
        try:
            if isdir(candidate):
                names.append(name)
        except OSError:
            continue
    return sorted(names)


def filter_unseen_dir_names(candidates: Sequence[str], seen: Iterable[str]) -> list[str]:
    """Return candidates not yet recorded in ``slowScanPromptSeen``."""
    seen_set = {str(item).strip() for item in seen if str(item).strip()}
    return [name for name in candidates if name not in seen_set]


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
