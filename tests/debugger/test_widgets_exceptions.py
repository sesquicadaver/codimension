# -*- coding: utf-8 -*-
"""T120: DebuggerExceptions widget smoke (pytest-qt / offscreen)."""

from __future__ import annotations

import pytest


@pytest.mark.debugger_session
def test_exceptions_add_clear_and_ignore(qtbot, skin_ready):
    """addException / clear / isIgnored after addExceptionFilter."""
    del skin_ready  # fixture side effect: GlobalData().skin for getIcon paths
    from debugger.excpt import DebuggerExceptions

    panel = DebuggerExceptions(None)
    qtbot.addWidget(panel)

    assert panel.getTotalClientExceptionCount() == 0
    panel.addException("ValueError", "boom", [])
    assert panel.getTotalClientExceptionCount() == 1

    panel.clear()
    assert panel.getTotalClientExceptionCount() == 0

    panel.ignoredExcptViewer.addExceptionFilter("ValueError")
    assert panel.isIgnored("ValueError") is True
