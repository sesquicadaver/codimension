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

"""Headless-capable analysis core (syntax / flow / cfg / execution / symbols / metrics / overlays / risk). No Qt."""

from __future__ import annotations

from typing import Any

__all__ = ["syntax", "flow", "cfg", "execution", "symbol_index", "metrics", "overlay", "risk_score"]


def __getattr__(name: str) -> Any:
    """Lazy submodule load so importing ``core.syntax`` does not pull siblings."""
    if name == "syntax":
        from . import syntax as _syntax

        return _syntax
    if name == "flow":
        from . import flow as _flow

        return _flow
    if name == "cfg":
        from . import cfg as _cfg

        return _cfg
    if name == "execution":
        from . import execution as _execution

        return _execution
    if name == "symbol_index":
        from . import symbol_index as _symbol_index

        return _symbol_index
    if name == "metrics":
        from . import metrics as _metrics

        return _metrics
    if name == "overlay":
        from . import overlay as _overlay

        return _overlay
    if name == "risk_score":
        from . import risk_score as _risk_score

        return _risk_score
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
