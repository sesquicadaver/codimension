# -*- coding: utf-8 -*-
#
# codimension - file URI ↔ path helpers for DocumentStore (R224 / R235 / R246)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Load :class:`~core.document_snapshot.DocumentSnapshot` from ``file://`` URIs.

R235: workspace-bounded, size-capped loader with realpath containment checks.
R246: fd-relative ``openat`` from a preopened workspace root, ``O_NOFOLLOW`` /
``O_NONBLOCK``, reject non-regular files before read, canonical URI output.
"""

from __future__ import annotations

import os
import stat as stat_mod
from urllib.parse import unquote, urlparse

from core.document_snapshot import DocumentSnapshot
from core.document_store import DocumentLoader

DEFAULT_MAX_DOCUMENT_BYTES = 2 * 1024 * 1024

_O_RDONLY = getattr(os, "O_RDONLY", 0)
_O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)


def path_to_file_uri(path: str) -> str:
    """Return a canonical ``file://`` URI for a local absolute path.

    Uses :meth:`pathlib.Path.as_uri` so spaces and special characters are
    percent-encoded (R242; full URI policy hardening continues in R243).
    """
    from pathlib import Path

    abs_path = os.path.abspath(os.path.expanduser(path))
    return Path(abs_path).as_uri()


def file_uri_to_path(uri: str) -> str | None:
    """Parse a ``file://`` (or bare absolute) URI into a filesystem path.

    Rejects non-local authorities (anything other than empty / ``localhost``).
    Percent-encoded path segments are decoded (R246).
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


def _open_nofollow(dir_fd: int, name: str, flags: int) -> int:
    """``openat`` relative to ``dir_fd`` with ``O_NOFOLLOW`` when available."""
    return os.open(name, flags | _O_NOFOLLOW, dir_fd=dir_fd)


def _relative_parts_under_root(root_real: str, abs_path: str) -> tuple[str, ...] | None:
    """Return path components of ``abs_path`` under ``root_real``, or ``None``."""
    try:
        rel = os.path.relpath(os.path.abspath(abs_path), root_real)
    except ValueError:
        return None
    if not rel or rel == os.curdir:
        return None
    if rel.startswith(".." + os.sep) or rel == ".." or os.path.isabs(rel):
        return None
    parts = tuple(p for p in rel.split(os.sep) if p and p not in (".", ".."))
    if not parts or ".." in parts:
        return None
    return parts


def _open_fd_under_root(root: str, abs_path: str) -> int | None:
    """Open ``abs_path`` via preopened ``root`` + component ``openat`` (R246)."""
    root_real = os.path.realpath(root)
    parts = _relative_parts_under_root(root_real, abs_path)
    if parts is None:
        return None
    try:
        root_fd = os.open(root_real, _O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW)
    except OSError:
        # Root may be a symlink; allow directory open without NOFOLLOW on root only.
        try:
            root_fd = os.open(root_real, _O_RDONLY | _O_DIRECTORY)
        except OSError:
            return None
    dir_fd = root_fd
    opened_dirs: list[int] = []
    try:
        for index, part in enumerate(parts):
            is_last = index == len(parts) - 1
            if is_last:
                try:
                    return _open_nofollow(dir_fd, part, _O_RDONLY | _O_NONBLOCK)
                except OSError:
                    return None
            try:
                child_fd = _open_nofollow(dir_fd, part, _O_RDONLY | _O_DIRECTORY)
            except OSError:
                return None
            try:
                st = os.fstat(child_fd)
                if not stat_mod.S_ISDIR(st.st_mode):
                    os.close(child_fd)
                    return None
            except OSError:
                try:
                    os.close(child_fd)
                except OSError:
                    pass
                return None
            opened_dirs.append(child_fd)
            dir_fd = child_fd
        return None
    finally:
        for fd in reversed(opened_dirs):
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            os.close(root_fd)
        except OSError:
            pass


def _open_fd_direct(path: str) -> int | None:
    """Open ``path`` with ``O_NOFOLLOW|O_NONBLOCK`` when no workspace root is set."""
    flags = _O_RDONLY | _O_NOFOLLOW | _O_NONBLOCK
    try:
        return os.open(path, flags)
    except OSError:
        try:
            return os.open(path, _O_RDONLY | _O_NONBLOCK)
        except OSError:
            return None


def _read_capped(fd: int, max_bytes: int) -> bytes | None:
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
    return b"".join(chunks)


def load_document_from_uri(
    uri: str,
    *,
    language_id: str = "",
    workspace_root: str | None = None,
    extra_roots: tuple[str, ...] = (),
    max_bytes: int = DEFAULT_MAX_DOCUMENT_BYTES,
) -> DocumentSnapshot | None:
    """Read UTF-8 text for ``uri`` into a version-0 snapshot, or ``None`` on failure.

    When ``workspace_root`` (and optional ``extra_roots``) are set, the file is
    opened via fd-relative ``openat`` under a preopened root (R246). Non-regular
    files (FIFO/socket/dir) are rejected after ``fstat`` without blocking the
    GUI. Reads are capped at ``max_bytes``.
    """
    path = file_uri_to_path(uri)
    if path is None:
        return None
    abs_path = os.path.abspath(os.path.expanduser(path))

    roots: list[str] = []
    if workspace_root:
        roots.append(os.path.abspath(os.path.expanduser(workspace_root)))
    roots.extend(os.path.abspath(os.path.expanduser(r)) for r in extra_roots)

    fd: int | None = None
    if roots:
        for root in roots:
            fd = _open_fd_under_root(root, abs_path)
            if fd is not None:
                break
        if fd is None:
            return None
    else:
        fd = _open_fd_direct(abs_path)
        if fd is None:
            return None

    try:
        st = os.fstat(fd)
        if not stat_mod.S_ISREG(st.st_mode):
            return None
        if st.st_size > max_bytes:
            return None
        real = os.path.realpath(abs_path)
        if roots and not _path_under_roots(real, tuple(roots)):
            return None
        raw = _read_capped(fd, max_bytes)
        if raw is None:
            return None
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
    """Return a :class:`DocumentLoader` bound to ``workspace_root`` (R235 / R246)."""

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
