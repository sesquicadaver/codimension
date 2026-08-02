# -*- coding: utf-8 -*-
"""T102: continue / step-over / stop from STATE_IN_IDE."""

from __future__ import annotations

import pytest

from .session import (
    build_session,
    teardown_session,
    wait_state,
    wait_until,
    write_script,
)


@pytest.mark.debugger_session
def test_continue_finishes_session(tmp_path, qapp, force_stop_at_first_line):
    """remoteContinue from first-line stop should end the short script."""
    del force_stop_at_first_line
    from debugger.server import CodimensionDebugger

    script = write_script(tmp_path)
    _host, run_manager, debugger = build_session(qapp)

    try:
        run_manager.debug(str(script), False)
        assert wait_state(debugger, CodimensionDebugger.STATE_IN_IDE, qapp, timeout_s=15.0)

        debugger.remoteContinue()
        assert wait_state(debugger, CodimensionDebugger.STATE_STOPPED, qapp, timeout_s=15.0), (
            f"expected STATE_STOPPED after continue, got {debugger.getState()}"
        )
    finally:
        teardown_session(debugger, run_manager, qapp)


@pytest.mark.debugger_session
def test_step_over_then_stop(tmp_path, qapp, force_stop_at_first_line):
    """remoteStepOver keeps the session alive; stopDebugging ends it."""
    del force_stop_at_first_line
    from debugger.server import CodimensionDebugger

    script = write_script(
        tmp_path,
        body=("a = 1\nb = 2\nc = 3\nd = 4\nprint(a + b + c + d)\n"),
    )
    _host, run_manager, debugger = build_session(qapp)

    try:
        run_manager.debug(str(script), False)
        assert wait_state(debugger, CodimensionDebugger.STATE_IN_IDE, qapp, timeout_s=15.0)

        debugger.remoteStepOver()
        # After step: client runs then returns to IDE (or finishes if few lines).
        assert wait_until(
            lambda: debugger.getState()
            in (CodimensionDebugger.STATE_IN_IDE, CodimensionDebugger.STATE_STOPPED),
            qapp,
            timeout_s=15.0,
        )
        if debugger.getState() == CodimensionDebugger.STATE_IN_IDE:
            debugger.stopDebugging()
            assert wait_state(debugger, CodimensionDebugger.STATE_STOPPED, qapp, timeout_s=15.0)
        else:
            assert debugger.getState() == CodimensionDebugger.STATE_STOPPED
    finally:
        teardown_session(debugger, run_manager, qapp)
