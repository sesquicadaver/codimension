# -*- coding: utf-8 -*-
"""T120: DebuggerBreakWatchPoints widget smoke (pytest-qt / offscreen)."""

from __future__ import annotations

import pytest


@pytest.mark.debugger_session
def test_break_watch_points_add_and_clear(qtbot, widget_debugger):
    """Add a breakpoint via model; panel.clear() resets getCounts()."""
    from debugger.bpwp import DebuggerBreakWatchPoints
    from debugger.breakpoint import Breakpoint

    _host, debugger = widget_debugger
    model = debugger.getBreakPointModel()
    panel = DebuggerBreakWatchPoints(None, debugger)
    qtbot.addWidget(panel)

    assert model.getCounts() == (0, 0)
    model.addBreakpoint(Breakpoint("/tmp/cdm_t120_bp.py", 1))
    assert model.getCounts() == (1, 0)
    assert model.rowCount() == 1

    panel.clear()
    assert model.getCounts() == (0, 0)
    assert model.rowCount() == 0
