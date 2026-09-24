# -*- coding: utf-8 -*-
"""R270: project scan cancel timeout keeps retired QThread ownership."""

from __future__ import annotations

import importlib
import sys
import threading
import time
from pathlib import Path

import pytest

_CODIM = Path(__file__).resolve().parents[1] / "codimension"


def _purge_stub_ui_for_project() -> None:
    """Drop incomplete ``ui`` stubs so ``utils.project`` can import real ``ui.qt``."""
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
    """Drop both ``utils.project`` and ``codimension.utils.project`` bindings."""
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


def _app():
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _pump(app, seconds: float = 0.05) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)


def test_r270_cancel_timeout_retires_live_thread(tmp_path: Path, monkeypatch) -> None:
    """Cancel join timeout must retire the handle, not drop the last QThread ref."""
    pytest.importorskip("PyQt5")
    from PyQt5.QtCore import QThread

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
        # Ignore cooperative cancel until the test releases — simulates blocked FS I/O.
        while not release.is_set():
            time.sleep(0.01)
        return {str(tmp_path) + "/", str(tmp_path / "a.py")}

    monkeypatch.setattr(project_mod, "scan_project_files", stuck_scan)

    project = CodimensionProject()
    project.fileName = str(proj_file)
    project.filesList = {str(tmp_path) + "/"}

    project._CodimensionProject__generateFilesList()  # noqa: SLF001
    assert started.wait(5), "scan did not start"
    active = project._CodimensionProject__scanThread  # noqa: SLF001
    assert active is not None and active.isRunning()

    project._CodimensionProject__cancelScan(join_ms=50)  # noqa: SLF001
    _pump(app, 0.05)

    assert project._CodimensionProject__scanThread is None  # noqa: SLF001
    retired = project._CodimensionProject__retiredScanThreads  # noqa: SLF001
    assert active in retired
    assert active.isRunning()
    assert active.parent() is None  # detached from Project QObject tree
    assert project.hasLiveScanThreads() is True

    # New scan must not start in parallel with a retired live thread.
    project._CodimensionProject__generateFilesList()  # noqa: SLF001
    assert project._CodimensionProject__scanCoalesce is True  # noqa: SLF001
    assert project._CodimensionProject__scanThread is None  # noqa: SLF001

    release.set()
    deadline = time.monotonic() + 5
    while active.isRunning() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    _pump(app, 0.2)

    assert active not in project._CodimensionProject__retiredScanThreads  # noqa: SLF001
    # Coalesced replacement should have started (and may already finish).
    replacement = project._CodimensionProject__scanThread  # noqa: SLF001
    assert replacement is None or isinstance(replacement, QThread)
    assert project.waitForScans(timeout_ms=3000) is True
    assert project.hasLiveScanThreads() is False


def test_r270_cancel_within_timeout_does_not_retire(tmp_path: Path, monkeypatch) -> None:
    """When the worker honors cancel quickly, no retired set entry is needed."""
    pytest.importorskip("PyQt5")

    _purge_stub_ui_for_project()
    project_mod, CodimensionProject = _reload_project_module()
    app = _app()

    from codimension.utils.project_scan import ScanCancelled

    proj_file = tmp_path / "demo.cdm3"
    proj_file.write_text("{}\n", encoding="utf-8")
    (tmp_path / "a.py").write_text("a=1\n", encoding="utf-8")

    started = threading.Event()

    def cooperative_scan(*_a, **kwargs):
        started.set()
        while True:
            cancel = kwargs.get("should_cancel")
            if cancel is not None and cancel():
                raise ScanCancelled("cancelled")
            time.sleep(0.01)

    monkeypatch.setattr(project_mod, "scan_project_files", cooperative_scan)

    project = CodimensionProject()
    project.fileName = str(proj_file)
    project.filesList = {str(tmp_path) + "/"}
    project._CodimensionProject__generateFilesList()  # noqa: SLF001
    assert started.wait(5)
    project._CodimensionProject__cancelScan(join_ms=2000)  # noqa: SLF001
    _pump(app, 0.2)
    assert project._CodimensionProject__retiredScanThreads == set()  # noqa: SLF001
    assert project.hasLiveScanThreads() is False
