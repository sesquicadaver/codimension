# -*- coding: utf-8 -*-
#
# Codimension - Python 3 experimental IDE
# Copyright (C) 2025  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Parse git status --porcelain output.

Format: https://git-scm.com/docs/git-status#_short_format
XY PATH or ?? PATH for untracked.
"""

import os.path

# Indicator IDs (must match getCustomIndicators)
IND_MODIFIED = 0
IND_ADDED = 1
IND_DELETED = 2
IND_UNTRACKED = 3
IND_CONFLICT = 4
IND_CLEAN = 5


def parse_status_output(git_root: str, output: str) -> list[tuple[str, int, str | None]]:
    """Parse `git status --porcelain` output.

    Args:
        git_root: Absolute path to repo root (with trailing sep).
        output: Raw stdout from git status --porcelain.

    Returns:
        List of (relative_path_from_repo_root, indicator_id, message).
        relative_path is from repo root; for dirs ends with os.path.sep.
    """
    result: list[tuple[str, int, str | None]] = []
    if not git_root.endswith(os.path.sep):
        git_root = git_root + os.path.sep

    for line in output.splitlines():
        line = line.rstrip("\n\r")
        if not line:
            continue

        # Untracked: "?? path"
        if line.startswith("?? "):
            path = line[3:].strip()
            if path:
                rel = _normalize_rel_path(path, git_root)
                result.append((rel, IND_UNTRACKED, None))
            continue

        # Standard: "XY path" or "XY path -> path2" (rename)
        if len(line) >= 4 and line[2] == " ":
            xy = line[:2]
            path_part = line[3:].strip()
            if " -> " in path_part:
                path = path_part.split(" -> ", 1)[1].strip()
            else:
                path = path_part

            if not path:
                continue

            ind_id = _xy_to_indicator(xy)
            rel = _normalize_rel_path(path, git_root)
            result.append((rel, ind_id, None))

    return result


def _xy_to_indicator(xy: str) -> int:
    """Map XY status to indicator ID."""
    x, y = xy[0], xy[1]
    # Unmerged (U, AA, DD, etc.)
    if x == "U" or y == "U" or x == "A" and y == "A" or x == "D" and y == "D":
        return IND_CONFLICT
    # Staged
    if x == "A":
        return IND_ADDED
    if x == "D":
        return IND_DELETED
    if x == "M" or x == "R" or x == "C":
        return IND_MODIFIED
    # Work tree
    if y == "A":
        return IND_ADDED
    if y == "D":
        return IND_DELETED
    if y == "M" or y == "?":
        return IND_MODIFIED if y == "M" else IND_UNTRACKED
    return IND_MODIFIED


def _normalize_rel_path(path: str, git_root: str) -> str:
    """Normalize path to relative from repo root; dirs end with sep."""
    full = os.path.normpath(os.path.join(git_root.rstrip(os.path.sep), path))
    root = git_root.rstrip(os.path.sep) + os.path.sep
    if full.startswith(root):
        rel = full[len(root) :].replace("/", os.path.sep)
    else:
        rel = path.replace("/", os.path.sep)
    if os.path.exists(full) and os.path.isdir(full) and not rel.endswith(os.path.sep):
        rel = rel + os.path.sep
    return rel
