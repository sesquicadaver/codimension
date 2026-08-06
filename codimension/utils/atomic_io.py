# -*- coding: utf-8 -*-
#
# codimension - atomic file writes
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Atomic write helpers (temp → fsync → os.replace) for configs and `.cdm3`."""

from __future__ import annotations

import os
import stat
import tempfile
from typing import Callable


def _existing_mode(path: str) -> int | None:
    """Return previous POSIX mode bits when ``path`` already exists."""
    try:
        return stat.S_IMODE(os.stat(path).st_mode)
    except OSError:
        return None


def _fsync_directory(directory: str) -> None:
    """Best-effort directory fsync so ``os.replace`` is durable."""
    try:
        dir_fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    except OSError:
        pass
    finally:
        os.close(dir_fd)


def _commit_temp(tmp_path: str, path: str, mode: int | None) -> None:
    """Replace ``path`` with ``tmp_path``, preserve/apply mode, fsync directory."""
    directory = os.path.dirname(path) or "."
    effective_mode = mode if mode is not None else _existing_mode(path)
    os.replace(tmp_path, path)
    if effective_mode is not None:
        try:
            os.chmod(path, effective_mode)
        except OSError:
            pass
    _fsync_directory(directory)


def atomic_write_text(
    path: str,
    content: str,
    *,
    encoding: str = "utf-8",
    mode: int | None = None,
) -> None:
    """Write ``content`` to ``path`` atomically.

    When ``mode`` is ``None`` and ``path`` already exists, the previous file
    mode is preserved. The parent directory is fsync'd after ``os.replace``.
    """
    directory = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=".cdm_atomic_", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        _commit_temp(tmp_path, path, mode)
        tmp_path = ""
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def atomic_write_bytes(path: str, content: bytes, *, mode: int | None = None) -> None:
    """Write binary ``content`` to ``path`` atomically."""
    directory = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=".cdm_atomic_", dir=directory)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        _commit_temp(tmp_path, path, mode)
        tmp_path = ""
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def atomic_write_via(path: str, writer: Callable[[str], None], *, mode: int | None = None) -> None:
    """Call ``writer(tmp_path)`` then atomically replace ``path``."""
    directory = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=".cdm_atomic_", dir=directory)
    os.close(fd)
    try:
        writer(tmp_path)
        with open(tmp_path, "rb") as handle:
            os.fsync(handle.fileno())
        _commit_temp(tmp_path, path, mode)
        tmp_path = ""
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
