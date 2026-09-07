# -*- coding: utf-8 -*-
#
# codimension - file URI ↔ path helpers for DocumentStore (R224 / R235)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Load :class:`~core.document_snapshot.DocumentSnapshot` from ``file://`` URIs.

R235: workspace-bounded, size-capped loader with realpath containment checks.
"""

from __future__ import annotations

import os
import stat as stat_mod
from urllib.parse import unquote, urlparse

from core.document_snapshot import DocumentSnapshot
from core.document_store import DocumentLoader

DEFAULT_MAX_DOCUMENT_BYTES = 2 * 1024 * 1024


def path_to_file_uri(path: str) -> str:
    """Return a minimal ``file://`` URI for a local absolute path."""
    abs_path = os.path.abspath(os.path.expanduser(path))
    return "file://" + abs_path


def file_uri_to_path(uri: str) -> str | None:
    """Parse a ``file://`` (or bare absolute) URI into a filesystem path.

    Rejects non-local authorities (anything other than empty / ``localhost``).
    """
    text = (uri or "").strip()
    if not text:
        return None
    if text.startswith("file:"):
        parsed = urlparse(text)
        if parsed.scheme != "file":
            return None
        authority = (parsed.netloc or "").strip().lower()
        if authority not in ("", "localhost"):
            return None
        path = unquote(parsed.path or "")
        if not path:
            return None
        return path
    if os.path.isabs(text):
        return text
    return None


def _path_under_roots(real_path: str, roots: tuple[str, ...]) -> bool:
    for root in roots:
        root_real = os.path.realpath(root)
        root_sep = root_real if root_real.endswith(os.sep) else root_real + os.sep
        if real_path == root_real or real_path.startswith(root_sep):
            return True
    return False


def load_document_from_uri(
    uri: str,
    *,
    language_id: str = "",
    workspace_root: str | None = None,
    extra_roots: tuple[str, ...] = (),
    max_bytes: int = DEFAULT_MAX_DOCUMENT_BYTES,
) -> DocumentSnapshot | None:
    """Read UTF-8 text for ``uri`` into a version-0 snapshot, or ``None`` on failure.

    When ``workspace_root`` (and optional ``extra_roots``) are set, the realpath
    must stay inside those trees. Reads are capped at ``max_bytes``.
    """
    path = file_uri_to_path(uri)
    if path is None:
        return None
    flags = getattr(os, "O_RDONLY", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags | nofollow) if nofollow else os.open(path, flags)
    except OSError:
        return None
    try:
        st = os.fstat(fd)
        if not stat_mod.S_ISREG(st.st_mode):
            return None
        if st.st_size > max_bytes:
            return None
        real = os.path.realpath(path)
        roots: list[str] = []
        if workspace_root:
            roots.append(os.path.abspath(os.path.expanduser(workspace_root)))
        roots.extend(os.path.abspath(os.path.expanduser(r)) for r in extra_roots)
        if roots and not _path_under_roots(real, tuple(roots)):
            return None
        remaining = max_bytes
        chunks: list[bytes] = []
        while remaining > 0:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        if remaining == 0 and os.read(fd, 1):
            return None
        raw = b"".join(chunks)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
    canonical = path_to_file_uri(real)
    return DocumentSnapshot(uri=canonical, text=text, version=0, language_id=language_id)


def make_workspace_document_loader(
    workspace_root: str,
    *,
    extra_roots: tuple[str, ...] = (),
    max_bytes: int = DEFAULT_MAX_DOCUMENT_BYTES,
    language_id: str = "",
) -> DocumentLoader:
    """Return a :class:`DocumentLoader` bound to ``workspace_root`` (R235)."""

    root = os.path.abspath(os.path.expanduser(workspace_root))

    def _loader(uri: str) -> DocumentSnapshot | None:
        return load_document_from_uri(
            uri,
            language_id=language_id,
            workspace_root=root,
            extra_roots=extra_roots,
            max_bytes=max_bytes,
        )

    return _loader


__all__ = [
    "DEFAULT_MAX_DOCUMENT_BYTES",
    "file_uri_to_path",
    "load_document_from_uri",
    "make_workspace_document_loader",
    "path_to_file_uri",
]
