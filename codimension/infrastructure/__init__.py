# -*- coding: utf-8 -*-
#
# codimension - headless infrastructure facades (T082)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Headless infrastructure helpers (filesystem / io / process / LSP).

Submodules are imported on attribute access so ``from infrastructure.X``
does not pull every sibling (avoids smoke-path cycles via filesystem →
``codimension.utils`` when only LSP helpers are needed).
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "ffi_bindings",
    "ffi_structural",
    "filesystem",
    "file_uri",
    "io",
    "lsp_framing",
    "lsp_position_codec",
    "lsp_process",
    "lsp_semantic",
    "process",
    "tree_sitter_structural",
]

_SUBMODULES = frozenset(__all__)


def __getattr__(name: str) -> Any:
    """Lazy-load known infrastructure submodules."""
    if name in _SUBMODULES:
        module = import_module(f".{name}", __name__)
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
