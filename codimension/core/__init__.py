# -*- coding: utf-8 -*-
#
# codimension - headless analysis core (M5)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Headless-capable analysis core (syntax / flow / execution / symbols / metrics). No Qt."""

from __future__ import annotations

from typing import Any

__all__ = ["syntax", "flow", "execution", "symbol_index", "metrics"]


def __getattr__(name: str) -> Any:
    """Lazy submodule load so importing ``core.syntax`` does not pull siblings."""
    if name == "syntax":
        from . import syntax as _syntax

        return _syntax
    if name == "flow":
        from . import flow as _flow

        return _flow
    if name == "execution":
        from . import execution as _execution

        return _execution
    if name == "symbol_index":
        from . import symbol_index as _symbol_index

        return _symbol_index
    if name == "metrics":
        from . import metrics as _metrics

        return _metrics
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
