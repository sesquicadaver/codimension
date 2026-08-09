# -*- coding: utf-8 -*-
#
# codimension - graphics python two-way code editor and analyzer
# Copyright (C) 2026  Codimension Team
# The license is described in the LICENSE file at the root directory.
#
# pylint: disable=C0305

"""File/directory pickers that avoid Qt non-native dialog freezes.

``QFileDialog`` with ``DontUseNativeDialog`` walks the filesystem with a
synchronous model and often hangs on large home directories. Prefer the
platform dialog and only fall back when a start path is invalid.
"""

from __future__ import annotations

import os

from .qt import QDir, QFileDialog


def _safe_start_dir(start_path: str | None) -> str:
    """Return an existing directory path for dialog start location."""
    if start_path:
        expanded = os.path.expanduser(str(start_path).strip())
        if expanded:
            candidate = os.path.abspath(expanded)
            if os.path.isfile(candidate):
                candidate = os.path.dirname(candidate)
            if os.path.isdir(candidate):
                return candidate
    return QDir.homePath()


def select_existing_directory(parent, title: str, start_path: str | None = None) -> str:
    """Native directory picker; empty string if cancelled."""
    start = _safe_start_dir(start_path)
    # Do not set DontUseNativeDialog — native pickers stay responsive.
    path = QFileDialog.getExistingDirectory(
        parent,
        title,
        start,
        QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks,
    )
    return os.path.normpath(path) if path else ""


def select_open_file(
    parent,
    title: str,
    start_path: str | None = None,
    name_filter: str = "All Files (*)",
) -> str:
    """Native open-file picker; empty string if cancelled."""
    start = _safe_start_dir(start_path)
    selected = QFileDialog.getOpenFileName(parent, title, start, name_filter)
    if isinstance(selected, tuple):
        selected = selected[0]
    return os.path.normpath(selected) if selected else ""
