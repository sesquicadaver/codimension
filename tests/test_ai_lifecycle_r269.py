# -*- coding: utf-8 -*-
"""R269: AI QThread lifecycle — deleteLater + shutdown wait before parent teardown."""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

pytest.importorskip("PyQt5")

from core.ai_tasks import AiTaskKind, AiTaskRequest  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402
from ui.aiworker import AiTaskDriver  # noqa: E402


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _pump(app: QApplication, seconds: float = 0.05) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)


def test_r269_shutdown_idle_returns_true() -> None:
    _app()
    driver = AiTaskDriver()
    assert driver.shutdown(timeout_ms=100) is True
    assert driver.isInProcess() is False


def test_r269_shutdown_waits_for_running_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _app()
    started = {"ok": False}

    def slow_run(request, progress=None, should_cancel=None):  # noqa: ANN001
        del request, progress
        started["ok"] = True
        for _ in range(50):
            if should_cancel is not None and should_cancel():
                break
            time.sleep(0.02)
        return SimpleNamespace(
            kind=AiTaskKind.CHAT,
            title="t",
            text="done",
            file_path="",
            symbol_name="",
            backend_name="fake",
            docstring_target=None,
        )

    monkeypatch.setattr("ui.aiworker.run_ai_task", slow_run)
    driver = AiTaskDriver()
    err = driver.start(AiTaskRequest(kind=AiTaskKind.CHAT, title="t", chat_message="hi"))
    assert err is None
    _pump(app, 0.1)
    assert started["ok"] is True
    assert driver.isInProcess() is True
    assert driver.shutdown(timeout_ms=3000) is True
    _pump(app, 0.1)
    assert driver.isInProcess() is False


def test_r269_shutdown_timeout_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the worker ignores cancel, shutdown must report failure (do not tear down)."""
    app = _app()

    def stuck_run(request, progress=None, should_cancel=None):  # noqa: ANN001
        del request, progress, should_cancel
        time.sleep(2.0)
        return SimpleNamespace(
            kind=AiTaskKind.CHAT,
            title="t",
            text="late",
            file_path="",
            symbol_name="",
            backend_name="fake",
            docstring_target=None,
        )

    monkeypatch.setattr("ui.aiworker.run_ai_task", stuck_run)
    driver = AiTaskDriver()
    assert driver.start(AiTaskRequest(kind=AiTaskKind.CHAT, title="t", chat_message="x")) is None
    _pump(app, 0.05)
    assert driver.isInProcess() is True
    assert driver.shutdown(timeout_ms=100) is False
    # Clean up so the process does not leak a live QThread into later tests.
    assert driver.shutdown(timeout_ms=5000) is True
    _pump(app, 0.1)
