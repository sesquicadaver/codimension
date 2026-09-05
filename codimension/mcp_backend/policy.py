# -*- coding: utf-8 -*-
#
# codimension - MCP workspace policy (R214)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Immutable allowed workspace root + scan resource budgets (R214).

Production startup must fix the filesystem authority via ``--workspace`` or
``CDM_MCP_WORKSPACE``. Clients cannot open arbitrary paths outside that root.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional

#: Absolute directory the MCP process may read (immutable after startup).
MCP_WORKSPACE_ENV = "CDM_MCP_WORKSPACE"
#: Max ``.py`` files loaded into the session (``0`` = unlimited — discouraged).
MCP_MAX_FILES_ENV = "CDM_MCP_MAX_FILES"
#: Max total source bytes loaded (``0`` = unlimited — discouraged).
MCP_MAX_BYTES_ENV = "CDM_MCP_MAX_BYTES"
#: Max path depth under the open root (``0`` = unlimited — discouraged).
MCP_MAX_DEPTH_ENV = "CDM_MCP_MAX_DEPTH"

DEFAULT_MAX_FILES = 10_000
DEFAULT_MAX_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_DEPTH = 32


class WorkspacePolicyError(PermissionError):
    """Raised when a path or startup config violates MCP workspace policy."""


class ResourceBudgetError(RuntimeError):
    """Raised when opening a workspace would exceed configured budgets."""


@dataclass(frozen=True, slots=True)
class WorkspacePolicy:
    """Fail-closed filesystem + scan limits for one MCP process."""

    allowed_root: str
    max_files: int = DEFAULT_MAX_FILES
    max_bytes: int = DEFAULT_MAX_BYTES
    max_depth: int = DEFAULT_MAX_DEPTH

    def __post_init__(self) -> None:
        """Normalize and validate the allowed root / budgets."""
        root = os.path.realpath(os.path.expanduser(self.allowed_root))
        if not root:
            raise WorkspacePolicyError("allowed_root must be non-empty")
        if not os.path.isdir(root):
            raise WorkspacePolicyError(f"allowed workspace root is not a directory: {root}")
        object.__setattr__(self, "allowed_root", root)
        for name, value in (
            ("max_files", self.max_files),
            ("max_bytes", self.max_bytes),
            ("max_depth", self.max_depth),
        ):
            if int(value) < 0:
                raise WorkspacePolicyError(f"{name} must be >= 0, got {value}")


def _parse_nonneg_int(raw: str, *, default: int, label: str) -> int:
    text = (raw or "").strip()
    if not text:
        return default
    try:
        value = int(text)
    except ValueError as exc:
        raise WorkspacePolicyError(f"{label} must be an integer, got {raw!r}") from exc
    if value < 0:
        raise WorkspacePolicyError(f"{label} must be >= 0, got {value}")
    return value


def resolve_under_allowed_root(allowed_root: str, path: str) -> str:
    """Return realpath of ``path`` if it stays under ``allowed_root``."""
    root = os.path.realpath(allowed_root)
    candidate = path if os.path.isabs(path) else os.path.join(root, path)
    real = os.path.realpath(os.path.expanduser(candidate))
    root_sep = root if root.endswith(os.sep) else root + os.sep
    if real != root and not real.startswith(root_sep):
        raise WorkspacePolicyError(f"path escapes allowed workspace root: {path}")
    return real


def depth_under_root(root: str, path: str) -> int:
    """Return directory depth of ``path`` relative to ``root`` (0 at root)."""
    root_real = os.path.realpath(root)
    path_real = os.path.realpath(path)
    if path_real == root_real:
        return 0
    rel = os.path.relpath(path_real, root_real)
    if rel.startswith(".."):
        raise WorkspacePolicyError(f"path escapes root for depth check: {path}")
    return len(rel.split(os.sep))


def policy_from_environ(
    environ: Optional[Mapping[str, str]] = None,
    *,
    workspace_cli: str | None = None,
) -> WorkspacePolicy:
    """Build policy from ``--workspace`` / env (fail-closed when root missing)."""
    env: Mapping[str, str] = os.environ if environ is None else environ
    raw = (workspace_cli or "").strip() or str(env.get(MCP_WORKSPACE_ENV, "")).strip()
    if not raw:
        raise WorkspacePolicyError(f"MCP workspace root required via --workspace or {MCP_WORKSPACE_ENV}")
    return WorkspacePolicy(
        allowed_root=raw,
        max_files=_parse_nonneg_int(
            str(env.get(MCP_MAX_FILES_ENV, "")),
            default=DEFAULT_MAX_FILES,
            label=MCP_MAX_FILES_ENV,
        ),
        max_bytes=_parse_nonneg_int(
            str(env.get(MCP_MAX_BYTES_ENV, "")),
            default=DEFAULT_MAX_BYTES,
            label=MCP_MAX_BYTES_ENV,
        ),
        max_depth=_parse_nonneg_int(
            str(env.get(MCP_MAX_DEPTH_ENV, "")),
            default=DEFAULT_MAX_DEPTH,
            label=MCP_MAX_DEPTH_ENV,
        ),
    )


def require_workspace_policy_or_exit(
    environ: Optional[Mapping[str, str]] = None,
    *,
    workspace_cli: str | None = None,
) -> WorkspacePolicy:
    """CLI helper: stderr + exit 1 when workspace policy cannot be built."""
    import sys

    try:
        return policy_from_environ(environ, workspace_cli=workspace_cli)
    except (WorkspacePolicyError, OSError) as exc:
        sys.stderr.write(f"codimension-mcp: {exc}\n")
        raise SystemExit(1) from exc


__all__ = [
    "DEFAULT_MAX_BYTES",
    "DEFAULT_MAX_DEPTH",
    "DEFAULT_MAX_FILES",
    "MCP_MAX_BYTES_ENV",
    "MCP_MAX_DEPTH_ENV",
    "MCP_MAX_FILES_ENV",
    "MCP_WORKSPACE_ENV",
    "ResourceBudgetError",
    "WorkspacePolicy",
    "WorkspacePolicyError",
    "depth_under_root",
    "policy_from_environ",
    "require_workspace_policy_or_exit",
    "resolve_under_allowed_root",
]
