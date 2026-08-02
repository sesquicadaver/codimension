# -*- coding: utf-8 -*-
"""T101: debug session stops at first line (session-first e2e)."""

from __future__ import annotations

from pathlib import Path

import pytest

from .session import (
    build_session,
    teardown_session,
    wait_state,
    wait_until,
    write_script,
)


def _paths_match(reported: str, script: Path) -> bool:
    """Client may report absolute path; compare resolved paths when possible."""
    try:
        return Path(reported).resolve() == Path(script).resolve()
    except OSError:
        return Path(reported).name == Path(script).name


@pytest.mark.debugger_session
def test_stop_at_first_line(tmp_path, qapp, force_stop_at_first_line):
    """Redirected debug of a temp script reaches STATE_IN_IDE + sigClientLine."""
    del force_stop_at_first_line
    from debugger.server import CodimensionDebugger

    script = write_script(tmp_path)
    host, run_manager, debugger = build_session(qapp)

    lines: list[tuple[str, int, bool]] = []
    debugger.sigClientLine.connect(lambda path, line, is_stack: lines.append((path, line, is_stack)))

    try:
        run_manager.debug(str(script), False)
        assert wait_state(debugger, CodimensionDebugger.STATE_IN_IDE, qapp, timeout_s=15.0), (
            f"expected STATE_IN_IDE, got {debugger.getState()}; host={host.switch_calls}; "
            f"status={host.status_messages}"
        )
        assert wait_until(lambda: len(lines) >= 1, qapp, timeout_s=2.0)
        path, line, _is_stack = lines[0]
        assert _paths_match(path, script)
        assert line >= 1
        assert host.debugMode is True
        assert True in host.switch_calls
    finally:
        teardown_session(debugger, run_manager, qapp)
