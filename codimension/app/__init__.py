# -*- coding: utf-8 -*-
#
# codimension - graphics python two-way code editor and analyzer
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Application layer façades (headless; no widgets).

R101 introduces ``ApplicationServices`` for project load/unload hooks.
R102 routes UI open/unload through this package.
"""

from __future__ import annotations

from typing import Any

__all__ = ["ApplicationServices"]


def __getattr__(name: str) -> Any:
    """Lazy export so ``import codimension.app`` stays free of side effects."""
    if name == "ApplicationServices":
        from .services import ApplicationServices as _ApplicationServices

        return _ApplicationServices
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
