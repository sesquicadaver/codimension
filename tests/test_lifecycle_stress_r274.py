# -*- coding: utf-8 -*-
"""R274: lifecycle stress — AI/scan close paths and smoke without os._exit."""

from __future__ import annotations

import gc
import importlib
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("PyQt5")

from core.ai_tasks import AiTaskKind, AiTaskRequest  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402
from ui.aiworker import AiTaskDriver  # noqa: E402
from utils.background_task_registry import BackgroundTaskRegistry  # noqa: E402

_CODIM = Path(__file__).resolve().parents[1] / "codimension"
_ROOT = Path(__file__).resolve().parents[1]
_AI_STRESS_COUNT = 50  # CI-friendly stand-in for the audit's 500-task soak


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _pump(app: QApplication, seconds: float = 0.05) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)


def _ok_result() -> SimpleNamespace:
    return SimpleNamespace(
        kind=AiTaskKind.CHAT,
        title="t",
        text="done",
        file_path="",
        symbol_name="",
        backend_name="fake",
        docstring_target=None,
    )


@pytest.fixture
def qapp():
    """Shared QApplication with event draining between AI lifecycle tests."""
    app = _app()
    yield app
    _pump(app, 0.15)


@pytest.fixture
def ai_driver(qapp):
    """AiTaskDriver that is always shut down before the next test."""
    driver = AiTaskDriver()
    yield driver
    try:
        driver.shutdown(timeout_ms=5000)
    finally:
        _pump(qapp, 0.2)


def _purge_stub_ui_for_project() -> None:
    dirty = False
    for name in list(sys.modules):
        if name != "ui" and not name.startswith("ui."):
            continue
        mod = sys.modules.get(name)
        path = getattr(mod, "__file__", None) or ""
        if not path or "codimension/ui" not in path.replace("\\", "/"):
            del sys.modules[name]
            dirty = True
    if dirty:
        importlib.invalidate_caches()
    if str(_CODIM) not in sys.path:
        sys.path.insert(0, str(_CODIM))


def _reload_project_module():
    for name in ("utils.project", "codimension.utils.project"):
        sys.modules.pop(name, None)
    for pkg_name in ("utils", "codimension.utils"):
        pkg = sys.modules.get(pkg_name)
        if pkg is not None and hasattr(pkg, "project"):
            delattr(pkg, "project")
    importlib.invalidate_caches()
    from codimension.utils import project as project_mod
    from codimension.utils.project import CodimensionProject

    return project_mod, CodimensionProject


def test_r274_ai_active_then_shutdown_quiesces(ai_driver, qapp, monkeypatch: pytest.MonkeyPatch) -> None:
    """AI active → close-equivalent shutdown must stop the worker."""
    started = threading.Event()

    def slow_run(request, progress=None, should_cancel=None):  # noqa: ANN001
        del request, progress
        started.set()
        for _ in range(100):
            if should_cancel is not None and should_cancel():
                break
            time.sleep(0.01)
        return _ok_result()

    monkeypatch.setattr("ui.aiworker.run_ai_task", slow_run)
    assert ai_driver.start(AiTaskRequest(kind=AiTaskKind.CHAT, title="t", chat_message="x")) is None
    assert started.wait(5)
    _pump(qapp, 0.05)
    assert ai_driver.isInProcess() is True
    assert ai_driver.shutdown(timeout_ms=5000) is True
    _pump(qapp, 0.1)
    assert ai_driver.isInProcess() is False


def test_r274_ai_cancel_then_immediate_shutdown(ai_driver, qapp, monkeypatch: pytest.MonkeyPatch) -> None:
    """Cancel then shutdown must not leave a live QThread."""
    started = threading.Event()

    def slow_run(request, progress=None, should_cancel=None):  # noqa: ANN001
        del request, progress
        started.set()
        while True:
            if should_cancel is not None and should_cancel():
                return _ok_result()
            time.sleep(0.01)

    monkeypatch.setattr("ui.aiworker.run_ai_task", slow_run)
    assert ai_driver.start(AiTaskRequest(kind=AiTaskKind.CHAT, title="t", chat_message="x")) is None
    assert started.wait(5)
    ai_driver.cancel()
    assert ai_driver.shutdown(timeout_ms=3000) is True
    _pump(qapp, 0.1)
    assert ai_driver.isInProcess() is False


def test_r274_many_ai_tasks_leave_no_live_thread(ai_driver, qapp, monkeypatch: pytest.MonkeyPatch) -> None:
    """Repeated AI tasks must not retain a running worker thread."""

    def instant_run(request, progress=None, should_cancel=None):  # noqa: ANN001
        del request, progress, should_cancel
        return _ok_result()

    monkeypatch.setattr("ui.aiworker.run_ai_task", instant_run)
    for i in range(_AI_STRESS_COUNT):
        err = ai_driver.start(AiTaskRequest(kind=AiTaskKind.CHAT, title=f"t{i}", chat_message="x"))
        assert err is None
        deadline = time.monotonic() + 5
        while ai_driver.isInProcess() and time.monotonic() < deadline:
            qapp.processEvents()
            time.sleep(0.005)
        assert ai_driver.isInProcess() is False, f"stuck after task {i}"
        _pump(qapp, 0.02)
    assert ai_driver.shutdown(timeout_ms=1000) is True
    _pump(qapp, 0.1)
    assert ai_driver.isInProcess() is False


def test_r274_blocking_scan_switch_and_close(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Blocking scan (>join timeout) survives switch; close waits for quiescence."""
    _purge_stub_ui_for_project()
    project_mod, CodimensionProject = _reload_project_module()
    app = _app()

    proj_file = tmp_path / "demo.cdm3"
    proj_file.write_text('{"uuid": "00000000-0000-0000-0000-000000000001"}\n', encoding="utf-8")
    (tmp_path / "a.py").write_text("a=1\n", encoding="utf-8")

    started = threading.Event()
    release = threading.Event()

    def stuck_scan(*_a, **_kwargs):
        started.set()
        while not release.is_set():
            time.sleep(0.01)
        return {str(tmp_path) + "/", str(tmp_path / "a.py")}

    monkeypatch.setattr(project_mod, "scan_project_files", stuck_scan)

    project = CodimensionProject()
    project.fileName = str(proj_file)
    project.filesList = {str(tmp_path) + "/"}
    try:
        project._CodimensionProject__generateFilesList()  # noqa: SLF001
        assert started.wait(5)

        # Project switch / unload path: cancel with short join → retire (parent detached).
        project._CodimensionProject__cancelScan(join_ms=50)  # noqa: SLF001
        _pump(app, 0.05)
        assert project.hasLiveScanThreads() is True
        retired = list(project._CodimensionProject__retiredScanThreads)  # noqa: SLF001
        assert len(retired) >= 1
        assert all(t.parent() is None for t in retired)

        # Forced GC after detach must keep the Python ownership set alive (R274).
        held = list(retired)
        while gc.collect():
            pass
        assert project.hasLiveScanThreads() is True
        assert all(t.isRunning() for t in held)

        # Application-close equivalent: registry wait.
        reg = BackgroundTaskRegistry()
        reg.register(
            "project_scan",
            cancel=project.requestScanCancel,
            wait=project.waitForScans,
            is_active=project.hasLiveScanThreads,
        )
        reg.request_shutdown()
        assert reg.wait_all(timeout_ms=80) is False
        release.set()
        assert reg.wait_all(timeout_ms=5000) is True
        assert project.hasLiveScanThreads() is False
        _pump(app, 0.1)
    finally:
        release.set()
        project.waitForScans(timeout_ms=5000)
        _pump(app, 0.2)


def test_r274_smoke_script_default_path_has_no_unconditional_os_exit() -> None:
    """Default CI smoke must exercise normal interpreter shutdown (R274 / P2-03)."""
    text = (_ROOT / "scripts" / "offscreen_gui_smoke.py").read_text(encoding="utf-8")
    assert "CDM_SMOKE_HARD_EXIT" in text
    assert 'os.environ.get("CDM_SMOKE_HARD_EXIT") == "1"' in text
