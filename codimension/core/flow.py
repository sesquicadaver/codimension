# -*- coding: utf-8 -*-
#
# codimension - headless control-flow parse API (T081)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Headless control-flow parse API (no Qt).

Uses the ``cdmcfparser`` product name (shim or C extension).
"""

from __future__ import annotations

from typing import Any


def _cdmcfparser():
    """Return the cdmcfparser module after ensuring shims are installed."""
    import importlib

    importlib.import_module("codimension.parsers")
    return importlib.import_module("cdmcfparser")


def parse_control_flow_from_memory(source: str) -> Any:
    """Parse Python source into a ControlFlow-compatible object."""
    return _cdmcfparser().getControlFlowFromMemory(source)


def parse_control_flow_from_file(path: str) -> Any:
    """Parse a Python file into a ControlFlow-compatible object."""
    return _cdmcfparser().getControlFlowFromFile(path)
