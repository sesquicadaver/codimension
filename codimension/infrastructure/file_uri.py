# -*- coding: utf-8 -*-
#
# codimension - file URI ↔ path helpers for DocumentStore (R224)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Load :class:`~core.document_snapshot.DocumentSnapshot` from ``file://`` URIs."""

from __future__ import annotations

import os
from urllib.parse import unquote, urlparse

from core.document_snapshot import DocumentSnapshot


def path_to_file_uri(path: str) -> str:
    """Return a minimal ``file://`` URI for a local absolute path."""
    abs_path = os.path.abspath(os.path.expanduser(path))
    return "file://" + abs_path


def file_uri_to_path(uri: str) -> str | None:
    """Parse a ``file://`` (or bare absolute) URI into a filesystem path."""
    text = (uri or "").strip()
    if not text:
        return None
    if text.startswith("file:"):
        parsed = urlparse(text)
        if parsed.scheme != "file":
            return None
        path = unquote(parsed.path or "")
        if not path:
            return None
        # file:///C:/... on Windows → /C:/...; leave as-is on POSIX.
        return path
    if os.path.isabs(text):
        return text
    return None


def load_document_from_uri(uri: str, *, language_id: str = "") -> DocumentSnapshot | None:
    """Read UTF-8 text for ``uri`` into a version-0 snapshot, or ``None`` on failure."""
    path = file_uri_to_path(uri)
    if path is None or not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except (OSError, UnicodeDecodeError):
        return None
    # Prefer a stable file:// key even when the caller passed a bare path.
    canonical = path_to_file_uri(path) if not uri.startswith("file:") else uri
    return DocumentSnapshot(uri=canonical, text=text, version=0, language_id=language_id)


__all__ = [
    "file_uri_to_path",
    "load_document_from_uri",
    "path_to_file_uri",
]
