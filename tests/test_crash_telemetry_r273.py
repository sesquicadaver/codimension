# -*- coding: utf-8 -*-
"""R273: faulthandler + crash_context telemetry."""

from __future__ import annotations

import os
from pathlib import Path

from codimension.utils.crash_telemetry import (
    collect_crash_context,
    crash_context_name,
    enable_crash_telemetry,
    native_crash_log_name,
    note_active_command,
    note_lifecycle,
    reset_for_tests,
    write_crash_context,
)


def test_r273_enable_writes_log_and_context(tmp_path: Path, monkeypatch) -> None:
    reset_for_tests()
    monkeypatch.setenv("CDM_COMMIT_SHA", "abc123def456")
    log_path = enable_crash_telemetry(
        str(tmp_path),
        version="9.9.9-test",
        pyqt_version="5.15.test",
        qt_version="5.15.qt",
    )
    assert log_path.endswith(native_crash_log_name())
    assert os.path.isfile(log_path)
    ctx = write_crash_context(str(tmp_path))
    assert ctx is not None
    assert ctx.endswith(crash_context_name())
    text = Path(ctx).read_text(encoding="utf-8")
    assert "codimension crash context (R273)" in text
    assert "version=9.9.9-test" in text
    assert "commit_sha=abc123def456" in text
    assert "pyqt=5.15.test" in text
    assert "qt=5.15.qt" in text
    assert "pid=" in text
    assert "crash_telemetry_enabled" in text
    reset_for_tests()


def test_r273_lifecycle_and_command_appear_in_context(tmp_path: Path) -> None:
    reset_for_tests()
    enable_crash_telemetry(str(tmp_path), version="1.0")
    note_lifecycle("project_load", detail="/tmp/demo.cdm3")
    note_active_command("AI Analyze Project")
    blob = collect_crash_context()
    assert "project_load" in blob
    assert "AI Analyze Project" in blob
    reset_for_tests()


def test_r273_enable_idempotent(tmp_path: Path) -> None:
    reset_for_tests()
    a = enable_crash_telemetry(str(tmp_path), version="1")
    b = enable_crash_telemetry(str(tmp_path), version="1")
    assert a == b
    reset_for_tests()
