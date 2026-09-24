# -*- coding: utf-8 -*-
"""R272: recoverable uncaught exceptions must not be process-fatal."""

from __future__ import annotations

from codimension.core.exception_containment import (
    UnrecoverableError,
    classify_uncaught,
    is_process_fatal,
)


def test_r272_callback_exception_contained_when_gui_ready() -> None:
    assert is_process_fatal(RuntimeError, application_ready=True) is False
    assert is_process_fatal(ValueError, application_ready=True) is False
    assert is_process_fatal(Exception, application_ready=True) is False
    assert classify_uncaught(RuntimeError, application_ready=True) == "recoverable"


def test_r272_bootstrap_still_fatal() -> None:
    assert is_process_fatal(RuntimeError, application_ready=False) is True
    assert classify_uncaught(RuntimeError, application_ready=False) == "fatal"


def test_r272_explicit_unrecoverable_is_fatal() -> None:
    assert is_process_fatal(UnrecoverableError, application_ready=True) is True
    assert is_process_fatal(MemoryError, application_ready=True) is True
    assert is_process_fatal(SystemError, application_ready=True) is True
    assert is_process_fatal(RecursionError, application_ready=True) is True
    assert is_process_fatal(SystemExit, application_ready=True) is True


def test_r272_keyboard_interrupt_not_fatal_classifier() -> None:
    assert is_process_fatal(KeyboardInterrupt, application_ready=True) is False
    assert classify_uncaught(KeyboardInterrupt, application_ready=True) == "interrupt"


def test_r272_hook_skips_exit_for_recoverable(monkeypatch) -> None:
    """exceptionHook must not call application.exit for contained errors."""
    import codimension.codimension as cdm

    calls = {"exit": 0, "critical": 0, "warning": 0}

    class _App:
        def exit(self, _code: int) -> None:
            calls["exit"] += 1

    class _GD:
        application = _App()
        mainWindow = object()

        def getLogViewerContent(self):  # pragma: no cover - unused via mainWindow
            return ""

    monkeypatch.setattr(cdm, "GlobalData", lambda: _GD())
    monkeypatch.setattr(cdm, "SETTINGS_DIR", "/tmp/")
    monkeypatch.setattr(
        cdm.QMessageBox,
        "critical",
        staticmethod(lambda *a, **k: calls.__setitem__("critical", calls["critical"] + 1)),
    )
    monkeypatch.setattr(
        cdm.QMessageBox,
        "warning",
        staticmethod(lambda *a, **k: calls.__setitem__("warning", calls["warning"] + 1)),
    )
    # Avoid writing real settings dir; open may still fail → savedOK False is fine.
    monkeypatch.setattr("builtins.open", lambda *a, **k: (_ for _ in ()).throw(OSError("no")))

    cdm.exceptionHook(RuntimeError, RuntimeError("boom"), None)
    assert calls["exit"] == 0
    assert calls["warning"] == 1
    assert calls["critical"] == 0


def test_r272_hook_exits_for_unrecoverable(monkeypatch) -> None:
    import codimension.codimension as cdm
    from codimension.core.exception_containment import UnrecoverableError

    calls = {"exit": 0}

    class _App:
        def exit(self, code: int) -> None:
            calls["exit"] = code

    class _GD:
        application = _App()
        mainWindow = object()

    monkeypatch.setattr(cdm, "GlobalData", lambda: _GD())
    monkeypatch.setattr(cdm, "SETTINGS_DIR", "/tmp/")
    monkeypatch.setattr(cdm.QMessageBox, "critical", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(cdm.QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr("builtins.open", lambda *a, **k: (_ for _ in ()).throw(OSError("no")))

    cdm.exceptionHook(UnrecoverableError, UnrecoverableError("die"), None)
    assert calls["exit"] == 1
