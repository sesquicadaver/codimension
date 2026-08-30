# -*- coding: utf-8 -*-
"""T050–T052: path-aware excludes, symlink bounds, async scan start latency."""

from __future__ import annotations

import importlib
import sys
import time
from os.path import realpath, sep
from pathlib import Path

import pytest

from codimension.utils.project_scan import (
    compile_basename_filters,
    is_excluded_by_absolute_paths,
    scan_project_files,
    should_exclude_basename,
)

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


def _mk_tree(root: Path) -> None:
    (root / "package" / "cache").mkdir(parents=True)
    (root / "package" / "cache" / "x.py").write_text("x = 1\n", encoding="utf-8")
    (root / "other" / "cache").mkdir(parents=True)
    (root / "other" / "cache" / "y.py").write_text("y = 1\n", encoding="utf-8")
    (root / "keep.py").write_text("k = 1\n", encoding="utf-8")


def test_t050_path_aware_exclude_does_not_kill_sibling_basename(tmp_path: Path) -> None:
    """exclude package/cache must not exclude other/cache (T050)."""
    _mk_tree(tmp_path)
    excl = [realpath(tmp_path / "package" / "cache")]
    files = scan_project_files(str(tmp_path) + sep, exclude_absolute_paths=excl)
    paths = {p.rstrip(sep) for p in files}
    assert realpath(tmp_path / "package" / "cache" / "x.py") not in paths
    assert realpath(tmp_path / "other" / "cache" / "y.py") in paths
    assert realpath(tmp_path / "keep.py") in paths


def test_t050_is_excluded_by_absolute_paths_prefix() -> None:
    assert is_excluded_by_absolute_paths("/a/b/c", ["/a/b"])
    assert not is_excluded_by_absolute_paths("/a/bx", ["/a/b"])


def test_t051_symlink_cycle_does_not_hang(tmp_path: Path) -> None:
    """Cycle via symlink must terminate (T051)."""
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "f.py").write_text("f=1\n", encoding="utf-8")
    (a / "to_b").symlink_to(b)
    (b / "to_a").symlink_to(a)
    files = scan_project_files(str(tmp_path) + sep)
    assert any(p.endswith("f.py") for p in files)
    # Finite result
    assert len(files) < 100


def test_t051_out_of_tree_symlink_not_followed(tmp_path: Path) -> None:
    """Symlink pointing outside project must not pull external files (T051)."""
    external = tmp_path / "external"
    external.mkdir()
    (external / "secret.py").write_text("s=1\n", encoding="utf-8")
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "ok.py").write_text("o=1\n", encoding="utf-8")
    (proj / "escape").symlink_to(external)
    files = scan_project_files(str(proj) + sep)
    assert not any("secret.py" in p for p in files)
    assert any(p.endswith("ok.py") for p in files)


def test_basename_filter_still_applies(tmp_path: Path) -> None:
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "c.pyc").write_text("", encoding="utf-8")
    (tmp_path / "m.py").write_text("m=1\n", encoding="utf-8")
    filters = compile_basename_filters([r"^__pycache__$"])
    files = scan_project_files(str(tmp_path) + sep, basename_filters=filters)
    assert not any("__pycache__" in p for p in files)
    assert any(p.endswith("m.py") for p in files)


def test_t052_async_scan_start_returns_quickly(tmp_path: Path) -> None:
    """Starting a background scan worker must not block GUI thread (T052)."""
    pytest.importorskip("PyQt5")
    from PyQt5.QtCore import QThread, pyqtSignal
    from PyQt5.QtWidgets import QApplication

    from codimension.utils.project_scan import scan_project_files

    class _ScanThread(QThread):
        sigDone = pyqtSignal(object)

        def __init__(self, root: str):
            QThread.__init__(self)
            self._root = root

        def run(self):
            self.sigDone.emit(scan_project_files(self._root))

    # Build ~5k files
    for i in range(50):
        d = tmp_path / f"d{i:03d}"
        d.mkdir()
        for j in range(100):
            (d / f"f{j:03d}.py").write_text("x=1\n", encoding="utf-8")

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    samples = []
    for _ in range(5):
        t0 = time.perf_counter()
        thread = _ScanThread(str(tmp_path) + sep)
        done = {"ok": False}

        def _on_done(_result, _done=done):
            _done["ok"] = True

        thread.sigDone.connect(_on_done)
        thread.start()
        samples.append((time.perf_counter() - t0) * 1000.0)
        deadline = time.time() + 30
        while not done["ok"] and time.time() < deadline:
            app.processEvents()
            time.sleep(0.01)
        assert done["ok"], "scan did not finish"
        thread.wait(5000)

    samples.sort()
    p95 = samples[int(len(samples) * 0.95) - 1] if len(samples) >= 2 else samples[-1]
    assert p95 <= 200.0, f"GUI-thread start latency p95={p95:.1f}ms samples={samples}"


def test_scan_cancelled_raises(tmp_path: Path) -> None:
    """B03: should_cancel aborts the walk with ScanCancelled."""
    from codimension.utils.project_scan import ScanCancelled

    for i in range(20):
        d = tmp_path / f"d{i}"
        d.mkdir()
        for j in range(10):
            (d / f"f{j}.py").write_text("x=1\n", encoding="utf-8")

    calls = {"n": 0}

    def cancel_after_few() -> bool:
        calls["n"] += 1
        return calls["n"] > 5

    with pytest.raises(ScanCancelled):
        scan_project_files(str(tmp_path) + sep, should_cancel=cancel_after_few)


def test_b03_project_scan_coalesce_and_interrupt(tmp_path: Path, monkeypatch) -> None:
    """B03: overlapping generateFilesList coalesces; interrupt stops I/O."""
    pytest.importorskip("PyQt5")
    import threading

    from PyQt5.QtWidgets import QApplication

    _purge_stub_ui_for_project()
    project_mod, CodimensionProject = _reload_project_module()
    from codimension.utils.project_scan import ScanCancelled

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    proj_file = tmp_path / "demo.cdm3"
    proj_file.write_text('{"uuid": "00000000-0000-0000-0000-000000000001"}\n', encoding="utf-8")
    (tmp_path / "a.py").write_text("a=1\n", encoding="utf-8")

    started = threading.Event()
    release = threading.Event()
    scans = {"n": 0}

    def slow_scan(*_a, **kwargs):
        scans["n"] += 1
        started.set()
        # Wait until interrupted or released.
        while not release.is_set():
            cancel = kwargs.get("should_cancel")
            if cancel is not None and cancel():
                raise ScanCancelled("cancelled")
            time.sleep(0.01)
        cancel = kwargs.get("should_cancel")
        if cancel is not None and cancel():
            raise ScanCancelled("cancelled")
        return {str(tmp_path) + sep, str(tmp_path / "a.py")}

    monkeypatch.setattr(project_mod, "scan_project_files", slow_scan)

    project = CodimensionProject()
    project.fileName = str(proj_file)
    project.filesList = {str(tmp_path) + sep}

    done = {"count": 0}

    def _complete():
        done["count"] += 1

    project._CodimensionProject__generateFilesList(on_complete=_complete)  # noqa: SLF001
    assert started.wait(5), "first scan did not start"
    # Second request while first is blocked → coalesce + interrupt.
    project._CodimensionProject__generateFilesList(on_complete=_complete)  # noqa: SLF001
    assert project._CodimensionProject__scanCoalesce is True  # noqa: SLF001
    thread = project._CodimensionProject__scanThread  # noqa: SLF001
    assert thread is not None
    assert thread.isInterruptionRequested()

    # Let the interrupted worker exit; coalesced rescan should start.
    deadline = time.time() + 10
    while scans["n"] < 2 and time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert scans["n"] >= 2, f"expected coalesced restart, scans={scans['n']}"
    release.set()

    deadline = time.time() + 10
    while done["count"] < 1 and time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert done["count"] >= 1
    project._CodimensionProject__cancelScan()  # noqa: SLF001


def test_b03_scan_failed_does_not_sync_on_gui(tmp_path: Path, monkeypatch) -> None:
    """B03: failure path must not call synchronous scan when QApplication exists."""
    pytest.importorskip("PyQt5")
    from PyQt5.QtWidgets import QApplication

    _purge_stub_ui_for_project()
    _, CodimensionProject = _reload_project_module()

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    proj_file = tmp_path / "demo.cdm3"
    proj_file.write_text("{}\n", encoding="utf-8")
    project = CodimensionProject()
    project.fileName = str(proj_file)
    project.filesList = {str(tmp_path) + sep}
    before = set(project.filesList)

    called = {"sync": False}

    def boom_sync(_self):
        called["sync"] = True

    monkeypatch.setattr(CodimensionProject, "_CodimensionProject__scanSync", boom_sync)
    gen = project._CodimensionProject__scanGeneration  # noqa: SLF001
    project._CodimensionProject__onScanFailed("boom", gen)  # noqa: SLF001
    assert called["sync"] is False
    assert project.filesList == before


def test_should_exclude_basename_pylintrc_exception() -> None:
    filters = compile_basename_filters([r"^\..*$"])
    assert should_exclude_basename(".git", filters)
    assert not should_exclude_basename(".pylintrc", filters)


def test_t051_watcher_symlink_cycle_bounded(tmp_path: Path) -> None:
    """Live Watcher must not explode on symlink cycles (T051)."""
    pytest.importorskip("PyQt5")
    from PyQt5.QtWidgets import QApplication

    from codimension.utils.watcher import Watcher

    if QApplication.instance() is None:
        QApplication([])

    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "f.py").write_text("f=1\n", encoding="utf-8")
    (a / "to_b").symlink_to(b)
    (b / "to_a").symlink_to(a)

    watcher = Watcher([], str(tmp_path) + sep)
    # Internal snapshot must stay small (no unbounded chain)
    snap = watcher._Watcher__fsSnapshot  # noqa: SLF001
    joined = " ".join(sorted(snap.keys()))
    assert "to_b/to_a/to_b" not in joined
    assert len(snap) < 20


def test_t051_watcher_out_of_tree_symlink_ignored(tmp_path: Path) -> None:
    """Watcher must not follow out-of-tree symlink targets (T051)."""
    pytest.importorskip("PyQt5")
    from PyQt5.QtWidgets import QApplication

    from codimension.utils.watcher import Watcher

    if QApplication.instance() is None:
        QApplication([])

    external = tmp_path / "external"
    external.mkdir()
    (external / "secret.py").write_text("s=1\n", encoding="utf-8")
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "ok.py").write_text("o=1\n", encoding="utf-8")
    (proj / "escape").symlink_to(external)

    watcher = Watcher([], str(proj) + sep)
    snap = watcher._Watcher__fsSnapshot  # noqa: SLF001
    blob = repr(snap)
    assert "secret.py" not in blob
    assert "ok.py" in blob


def test_t051_watcher_live_out_of_tree_symlink_ignored(tmp_path: Path) -> None:
    """Live FS event adding out-of-tree symlink must not enter snapshot (T051)."""
    pytest.importorskip("PyQt5")
    from PyQt5.QtWidgets import QApplication

    from codimension.utils.watcher import Watcher

    if QApplication.instance() is None:
        QApplication([])

    external = tmp_path / "external"
    external.mkdir()
    (external / "secret.py").write_text("s=1\n", encoding="utf-8")
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "ok.py").write_text("o=1\n", encoding="utf-8")

    watcher = Watcher([], str(proj) + sep)
    # Simulate live add: out-of-tree symlink dir
    (proj / "escape").symlink_to(external)
    watcher._Watcher__onDirChanged(str(proj) + sep)  # noqa: SLF001
    snap = watcher._Watcher__fsSnapshot  # noqa: SLF001
    blob = repr(snap)
    assert "escape" not in blob
    assert "secret.py" not in blob


def test_t050_watcher_path_aware_exclude(tmp_path: Path) -> None:
    """Watcher excludeAbsolutePaths must not kill sibling basename dirs (T050)."""
    pytest.importorskip("PyQt5")
    from PyQt5.QtWidgets import QApplication

    from codimension.utils.watcher import Watcher

    if QApplication.instance() is None:
        QApplication([])

    _mk_tree(tmp_path)
    excl = [realpath(tmp_path / "package" / "cache")]
    watcher = Watcher([], str(tmp_path) + sep, excludeAbsolutePaths=excl)
    snap = watcher._Watcher__fsSnapshot  # noqa: SLF001
    blob = repr(snap)
    assert "x.py" not in blob
    assert "y.py" in blob
