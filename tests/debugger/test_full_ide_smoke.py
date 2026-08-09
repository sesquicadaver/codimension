# -*- coding: utf-8 -*-
"""T130: full-IDE offscreen smoke (env-gated; not a PR blocker)."""

from __future__ import annotations

import os
import sys

import pytest

from .session import teardown_session, wait_state, write_script

pytestmark = [
    pytest.mark.full_ide,
    pytest.mark.skipif(
        os.environ.get("CDM_FULL_IDE_SMOKE") != "1",
        reason="Set CDM_FULL_IDE_SMOKE=1 to run full-IDE MainWindow smoke",
    ),
]


@pytest.fixture
def ide_env(_debugger_session_env, _isolate_from_collection_stubs):
    """Path/imp isolation without the plain ``qapp`` fixture (R1′)."""
    from utils.globals import resetGlobalDataForTests

    resetGlobalDataForTests()
    saved_out, saved_err = sys.stdout, sys.stderr
    yield
    sys.stdout, sys.stderr = saved_out, saved_err
    resetGlobalDataForTests()


def test_mainwindow_debug_stop_at_first_line(ide_env, tmp_path):
    """FakeSplash → CodimensionMainWindow → debug temp script → STATE_IN_IDE → stop."""
    del ide_env
    from debugger.server import CodimensionDebugger

    from .ide_bootstrap import build_main_window

    # Keep Recent/lastpositions out of the developer's real ~/.codimension3.
    main_window, app = build_main_window(settings_dir=str(tmp_path / "cdm-settings"))
    script = write_script(tmp_path)
    try:
        main_window._runManager.debug(str(script), False)
        assert wait_state(
            main_window._debugger,
            CodimensionDebugger.STATE_IN_IDE,
            app,
            timeout_s=30.0,
        ), f"expected STATE_IN_IDE, got {main_window._debugger.getState()}"
    finally:
        teardown_session(main_window._debugger, main_window._runManager, app)
        assert wait_state(
            main_window._debugger,
            CodimensionDebugger.STATE_STOPPED,
            app,
            timeout_s=10.0,
        ), f"expected STATE_STOPPED after teardown, got {main_window._debugger.getState()}"
        try:
            main_window.close()
        except Exception:
            pass
        app.processEvents()
