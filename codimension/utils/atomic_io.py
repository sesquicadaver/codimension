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
import tempfile
from typing import Callable


def atomic_write_text(
    path: str,
    content: str,
    *,
    encoding: str = "utf-8",
    mode: int | None = None,
) -> None:
    """Write ``content`` to ``path`` atomically; optional POSIX ``mode`` after replace."""
    directory = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=".cdm_atomic_", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
        tmp_path = ""  # replaced successfully
        if mode is not None:
            os.chmod(path, mode)
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
        os.replace(tmp_path, path)
        tmp_path = ""
        if mode is not None:
            os.chmod(path, mode)
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
        # Ensure durability of whatever writer produced
        with open(tmp_path, "rb") as handle:
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
        tmp_path = ""
        if mode is not None:
            os.chmod(path, mode)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
