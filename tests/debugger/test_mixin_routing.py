# -*- coding: utf-8 -*-
"""T111: MainWindowDebuggerMixin routing on MixinDebuggerHost."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from .session import build_session, teardown_session, wait_state, write_script


@pytest.mark.debugger_session
def test_switch_debug_mode_toggles_chrome(qapp, force_stop_at_first_line):
    """switchDebugMode(True/False) updates stub chrome without AttributeError."""
    del force_stop_at_first_line
    from .host import create_mixin_host

    host = create_mixin_host()
    host.switchDebugMode(True)
    assert host.debugMode is True
    assert True in host.switch_calls
    assert host.sbDebugState.visible is True
    assert host.sbLanguage.visible is False
    assert host._dbgGo.visible is True
    assert host._rightSideBar.enabled_tabs.get("debugger") is True
    assert host._rightSideBar.current == "debugger"

    host.switchDebugMode(False)
    assert host.debugMode is False
    assert False in host.switch_calls
    assert host.sbDebugState.visible is False
    assert host.sbLanguage.visible is True
    assert host._dbgGo.visible is False
    assert host._rightSideBar.enabled_tabs.get("debugger") is False
    # processEvents not required for stub chrome; keep qapp alive for Qt types
    qapp.processEvents()


@pytest.mark.debugger_session
def test_on_dbg_go_calls_remote_continue(tmp_path, qapp, force_stop_at_first_line):
    """_onDbgGo delegates to CodimensionDebugger.remoteContinue at STATE_IN_IDE."""
    del force_stop_at_first_line
    from debugger.server import CodimensionDebugger

    script = write_script(tmp_path)
    host, run_manager, debugger = build_session(qapp)
    original = debugger.remoteContinue
    debugger.remoteContinue = MagicMock(wraps=original)

    try:
        run_manager.debug(str(script), False)
        assert wait_state(debugger, CodimensionDebugger.STATE_IN_IDE, qapp, timeout_s=15.0)
        host._onDbgGo()
        assert debugger.remoteContinue.called
        assert wait_state(debugger, CodimensionDebugger.STATE_STOPPED, qapp, timeout_s=15.0)
    finally:
        debugger.remoteContinue = original
        teardown_session(debugger, run_manager, qapp)
