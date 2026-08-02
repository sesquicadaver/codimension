# -*- coding: utf-8 -*-
#
# codimension - headless brief/syntax parse API (T080)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Headless brief-module parse API (no Qt).

Uses the ``cdmpyparser`` product name (shim or C extension) via
``codimension.parsers`` installation so callers stay IDE-agnostic.
"""

from __future__ import annotations

from typing import Any


def _cdmpyparser():
    """Return the cdmpyparser module after ensuring shims are installed."""
    import importlib

    importlib.import_module("codimension.parsers")
    return importlib.import_module("cdmpyparser")


def parse_brief_from_memory(source: str, filename: str = "<string>") -> Any:
    """Parse Python source into a BriefModuleInfo-compatible object."""
    return _cdmpyparser().getBriefModuleInfoFromMemory(source, filename)


def parse_brief_from_file(path: str) -> Any:
    """Parse a Python file into a BriefModuleInfo-compatible object."""
    return _cdmpyparser().getBriefModuleInfoFromFile(path)
