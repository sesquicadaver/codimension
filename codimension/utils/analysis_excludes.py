# -*- coding: utf-8 -*-
#
# codimension - default analysis path excludes
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Default artifact directories excluded from project analysis.

``build/``, ``dist/``, and ``*.egg-info`` are setuptools/pip by-products. They
duplicate source trees and inflate unresolved-import noise. Auto-excluded like
project venv unless the user disables the IDE setting.
"""

from __future__ import annotations

import os
from os.path import isdir, join, realpath

# Top-level names under the project root (exact directory basenames).
DEFAULT_ARTIFACT_DIR_NAMES: tuple[str, ...] = (
    "build",
    "dist",
    ".eggs",
)


def list_default_artifact_excludes(project_dir: str | None) -> list[str]:
    """Absolute paths of existing default artifact dirs under ``project_dir``."""
    if not project_dir:
        return []
    root = realpath(project_dir)
    if not isdir(root):
        return []
    found: list[str] = []
    for name in DEFAULT_ARTIFACT_DIR_NAMES:
        candidate = join(root, name)
        if isdir(candidate):
            found.append(realpath(candidate))
    try:
        for entry in os.listdir(root):
            if entry.endswith(".egg-info"):
                candidate = join(root, entry)
                if isdir(candidate):
                    found.append(realpath(candidate))
    except OSError:
        pass
    return found


def auto_exclude_artifacts_enabled() -> bool:
    """IDE setting: auto-exclude build/dist/egg-info from analysis (default True)."""
    try:
        from .settings import Settings

        return bool(Settings()["autoExcludeBuildArtifacts"])
    except Exception:
        return True


def merge_analysis_exclude_paths(
    project_dir: str | None,
    user_excludes: list[str],
    *,
    enabled: bool | None = None,
) -> list[str]:
    """Merge user ``excludeFromAnalysis`` with default artifact dirs (deduped)."""
    if enabled is None:
        enabled = auto_exclude_artifacts_enabled()
    merged: list[str] = []
    seen: set[str] = set()
    for path in user_excludes:
        key = realpath(path)
        if key in seen:
            continue
        seen.add(key)
        merged.append(key)
    if enabled:
        for path in list_default_artifact_excludes(project_dir):
            key = realpath(path)
            if key in seen:
                continue
            seen.add(key)
            merged.append(key)
    return merged


def persist_artifact_excludes_to_project(project) -> list[str]:
    """Write default artifact dirs/names into project ``excludeFromAnalysis``.

    Returns the relative paths/names that were added. Used when the user
    explicitly chooses «Exclude build artifacts» in the unresolved-imports dialog.
    """
    if project is None or not project.isLoaded():
        return []
    project_dir = project.getProjectDir()
    root = realpath(project_dir)
    current = list(project.props.get("excludeFromAnalysis", []) or [])
    current_norm = {p.strip().rstrip("/\\") for p in current if p and p.strip()}
    current_abs = {
        realpath(p) if os.path.isabs(p) else realpath(join(root, p)) for p in current if p
    }
    added_rel: list[str] = []
    for abs_path in list_default_artifact_excludes(project_dir):
        if abs_path in current_abs:
            continue
        rel = os.path.relpath(abs_path, root)
        current.append(rel)
        current_abs.add(abs_path)
        current_norm.add(rel)
        added_rel.append(rel)
    for name in DEFAULT_ARTIFACT_DIR_NAMES:
        if name in current_norm:
            continue
        current.append(name)
        current_norm.add(name)
        added_rel.append(name)
    if added_rel:
        props = dict(project.props)
        props["excludeFromAnalysis"] = current
        project.updateProperties(props)
    return added_rel
