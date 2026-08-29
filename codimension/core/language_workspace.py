# -*- coding: utf-8 -*-
#
# codimension - workspace root / compile_commands discovery (R203)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Find language workspace roots and assess C++/Rust semantic readiness (R203)."""

from __future__ import annotations

import os
from typing import Sequence

from .semantic import SemanticReadiness


def find_marked_root(start_path: str, markers: Sequence[str]) -> str | None:
    """Walk upward from ``start_path`` until a marker file/dir is found.

    Returns the directory containing the marker, or ``None``.
    """
    if not markers:
        return None
    path = os.path.abspath(os.path.expanduser(start_path))
    if os.path.isfile(path):
        path = os.path.dirname(path)
    while True:
        for marker in markers:
            candidate = os.path.join(path, marker)
            if os.path.exists(candidate):
                return path
        parent = os.path.dirname(path)
        if parent == path:
            return None
        path = parent


def find_compile_commands_json(workspace_root: str) -> str | None:
    """Locate ``compile_commands.json`` under ``workspace_root`` (shallow).

    Checks the root itself, then common one-level build dirs
    (``build``, ``Build``, ``out``, ``cmake-build-debug``,
    ``cmake-build-release``).
    """
    root = os.path.abspath(os.path.expanduser(workspace_root))
    direct = os.path.join(root, "compile_commands.json")
    if os.path.isfile(direct):
        return direct
    for sub in (
        "build",
        "Build",
        "out",
        "cmake-build-debug",
        "cmake-build-release",
    ):
        candidate = os.path.join(root, sub, "compile_commands.json")
        if os.path.isfile(candidate):
            return candidate
    return None


def assess_rust_semantic_readiness(workspace_root: str) -> SemanticReadiness:
    """READY when ``Cargo.toml`` or ``rust-project.json`` is at the root."""
    root = os.path.abspath(os.path.expanduser(workspace_root))
    for marker in ("Cargo.toml", "rust-project.json"):
        if os.path.isfile(os.path.join(root, marker)):
            return SemanticReadiness.READY
    return SemanticReadiness.DEGRADED


def assess_cpp_semantic_readiness(workspace_root: str) -> SemanticReadiness:
    """READY only when ``compile_commands.json`` is found; else DEGRADED.

    DEGRADED means Tree-sitter / partial clangd may still run, but Codimension
    must **not** claim full diagnostics.
    """
    if find_compile_commands_json(workspace_root) is not None:
        return SemanticReadiness.READY
    return SemanticReadiness.DEGRADED


__all__ = [
    "assess_cpp_semantic_readiness",
    "assess_rust_semantic_readiness",
    "find_compile_commands_json",
    "find_marked_root",
]
