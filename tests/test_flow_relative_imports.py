# -*- coding: utf-8 -*-
"""Relative ImportFrom.level and half-open fromPart spans (A05)."""

from __future__ import annotations

from parsers.flow_ast import getControlFlowFromMemory


def test_flow_relative_import_levels():
    src = """
from .services import Client
from ..core import Config
from . import helpers
"""
    cf = getControlFlowFromMemory(src)
    texts = []
    for frag in cf.nsuite:
        if hasattr(frag, "getDisplayValue"):
            texts.append(frag.getDisplayValue())
        elif hasattr(frag, "displayValue"):
            texts.append(frag.displayValue)
    blob = "\n".join(texts)
    assert "from .services import Client" in blob
    assert "from ..core import Config" in blob
    assert "from . import helpers" in blob


def test_flow_from_part_half_open_slice():
    """fromPart.begin/end must be half-open: source[begin:end] == module display."""
    src = "from .services import Client\n"
    cf = getControlFlowFromMemory(src)
    assert cf.body.end == len(src)
    imports = [f for f in cf.nsuite if getattr(f, "fromPart", None) is not None]
    assert imports, "expected ImportFrom with fromPart"
    part = imports[0].fromPart
    assert src[part.begin : part.end] == ".services"


def test_control_flow_root_exclusive_end():
    src = "x = 1\n"
    cf = getControlFlowFromMemory(src)
    begin, end = cf.getAbsPosRange()
    assert begin == 0
    assert end == len(src)
    assert src[begin:end] == src
