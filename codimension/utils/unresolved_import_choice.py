# -*- coding: utf-8 -*-
#
# codimension - unresolved import choice (Qt-free helpers)
# Copyright (C) 2026  Codimension
#

"""Session helpers for unresolved-import exclude-vs-install choice."""

from __future__ import annotations

import os
from typing import Iterable

ACTION_SKIP = "skip"
ACTION_EXCLUDE = "exclude"
ACTION_INSTALL = "install"

# Session suppress: (project_dir, frozenset(packages)) after Skip.
_SKIPPED: set[tuple[str, frozenset[str]]] = set()


def clear_unresolved_import_skip_session() -> None:
    """Clear session Skip memory (tests)."""
    _SKIPPED.clear()


def mark_unresolved_import_skipped(project_dir: str, packages: Iterable[str]) -> None:
    """Remember Skip for this project/package set until IDE restart."""
    pkgs = frozenset(p for p in packages if p)
    if not project_dir or not pkgs:
        return
    _SKIPPED.add((os.path.realpath(project_dir), pkgs))


def should_offer_unresolved_import_choice(
    project,
    unresolved_packages: Iterable[str],
) -> bool:
    """True when a choice dialog is useful for this project/session."""
    if project is None or not getattr(project, "isLoaded", lambda: False)():
        return False
    packages = frozenset(p for p in unresolved_packages if p)
    if not packages:
        return False
    project_dir = os.path.realpath(project.getProjectDir())
    if (project_dir, packages) in _SKIPPED:
        return False
    return True
