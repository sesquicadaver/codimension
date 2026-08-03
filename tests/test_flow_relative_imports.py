# -*- coding: utf-8 -*-
"""Relative ImportFrom.level must appear in flow display values."""

from __future__ import annotations

from parsers.flow_ast import getControlFlowFromMemory


def test_flow_relative_import_levels():
    src = '''
from .services import Client
from ..core import Config
from . import helpers
'''
    cf = getControlFlowFromMemory(src)
    displays = []
    for frag in cf.nsuite:
        val = getattr(frag, "getDisplayValue", lambda: "")()
        if not val and hasattr(frag, "_display_value"):
            val = frag._display_value
        displays.append(val or getattr(frag, "display_value", ""))
    # Import fragments expose display via getDisplayValue
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
