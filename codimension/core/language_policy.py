# -*- coding: utf-8 -*-
#
# codimension - polyglot security policy gates (R202)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Deny-by-default effect gates for polyglot side effects (R202).

Descriptors never imply permission. Concrete capabilities (spawn, build
scripts, query-driver, …) must be checked before side effects. This module is
Qt-free and performs **no** process launch — only path validation.
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Iterable


class PolicyCapability(str, Enum):
    """Side-effect capabilities gated before polyglot actions."""

    TREE_PARSE = "tree_parse"
    LANGUAGE_SERVER_SPAWN = "language_server_spawn"
    PROJECT_METADATA_EXEC = "project_metadata_exec"
    BUILD_SCRIPT_EXEC = "build_script_exec"
    PROC_MACRO_EXEC = "proc_macro_exec"
    CHECK_COMMAND_EXEC = "check_command_exec"
    COMPILER_QUERY_EXEC = "compiler_query_exec"
    FORMATTER_EXEC = "formatter_exec"
    WORKSPACE_EDIT_APPLY = "workspace_edit_apply"
    BUILD_TASK_EXEC = "build_task_exec"


def allow_tree_parse() -> bool:
    """Return True — pure Tree-sitter parse has no process side effects (R205)."""
    return True


class LanguageServerSpawnError(PermissionError):
    """Raised when LANGUAGE_SERVER_SPAWN is denied."""

    def __init__(self, message: str, *, binary: str = "") -> None:
        self.binary = binary
        super().__init__(message)


def normalize_absolute_binary(path: str) -> str:
    """Return a normalized absolute path or raise :class:`LanguageServerSpawnError`.

    Relative paths, empty strings, and ``PATH``-style bare names are denied.
    Symlinks are resolved via :func:`os.path.realpath` when the path exists;
    non-existent absolute paths are still normalized (caller may check isfile).
    """
    raw = (path or "").strip()
    if not raw:
        raise LanguageServerSpawnError("language server binary path is empty", binary=path)
    if not os.path.isabs(raw):
        raise LanguageServerSpawnError(
            f"LANGUAGE_SERVER_SPAWN deny: binary must be an absolute path, got {raw!r}",
            binary=raw,
        )
    if os.path.exists(raw):
        return os.path.realpath(raw)
    return os.path.normpath(raw)


def require_language_server_spawn(
    binary: str,
    allowlist: Iterable[str],
    *,
    must_exist: bool = True,
) -> str:
    """Validate ``binary`` for :attr:`PolicyCapability.LANGUAGE_SERVER_SPAWN`.

    Deny-by-default: the binary must be absolute **and** present on
    ``allowlist`` (also absolute; compared after normalization / realpath).
    When ``must_exist`` is True (default), the path must be an existing file.

    Returns:
        Normalized absolute binary path safe to pass to ``Popen``.
    """
    resolved = normalize_absolute_binary(binary)
    allowed: set[str] = set()
    for entry in allowlist:
        try:
            allowed.add(normalize_absolute_binary(str(entry)))
        except LanguageServerSpawnError:
            continue
    if resolved not in allowed:
        raise LanguageServerSpawnError(
            f"LANGUAGE_SERVER_SPAWN deny: {resolved!r} is not on the configured absolute-binary allowlist",
            binary=resolved,
        )
    if must_exist and not os.path.isfile(resolved):
        raise LanguageServerSpawnError(
            f"LANGUAGE_SERVER_SPAWN deny: {resolved!r} is not an existing file",
            binary=resolved,
        )
    if must_exist and not os.access(resolved, os.X_OK):
        raise LanguageServerSpawnError(
            f"LANGUAGE_SERVER_SPAWN deny: {resolved!r} is not executable",
            binary=resolved,
        )
    return resolved


__all__ = [
    "LanguageServerSpawnError",
    "PolicyCapability",
    "allow_tree_parse",
    "normalize_absolute_binary",
    "require_language_server_spawn",
]
