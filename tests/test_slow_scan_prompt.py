# -*- coding: utf-8 -*-
"""Slow-scan ignore prompt helpers and project integration."""

from __future__ import annotations

import importlib
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from codimension.utils.slow_scan_prompt import (
    SLOW_SCAN_PROMPT_MS,
    ScanDirectoryTracker,
    is_prompt_seen,
    merge_prompt_seen,
    merge_unique_paths,
    project_relative_dir,
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


def test_project_relative_dir(tmp_path: Path) -> None:
    nested = tmp_path / "workbench" / "tools"
    nested.mkdir(parents=True)
    assert project_relative_dir(str(tmp_path), str(nested)) == "workbench/tools"
    assert project_relative_dir(str(tmp_path), str(tmp_path)) is None


def test_scan_tracker_picks_hottest_non_root(tmp_path: Path) -> None:
    tracker = ScanDirectoryTracker(str(tmp_path))
    root = str(tmp_path) + "/"
    hot = str(tmp_path / "workbench" / "tools") + "/"
    other = str(tmp_path / "src") + "/"
    tracker.note(root)
    time.sleep(0.02)
    tracker.note(hot)
    time.sleep(0.05)
    tracker.note(other)
    time.sleep(0.01)
    assert tracker.hot_directory() == hot


def test_merge_and_seen() -> None:
    assert merge_unique_paths(["a"], ["a", "b", "  "]) == ["a", "b"]
    assert merge_prompt_seen(["a"], ["b", "a"]) == ["a", "b"]
    assert is_prompt_seen("workbench/tools", ["workbench/tools"])
    assert not is_prompt_seen("workbench", ["workbench/tools"])


def test_on_directory_callback(tmp_path: Path) -> None:
    from codimension.utils.project_scan import scan_project_files

    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "b").mkdir()
    (tmp_path / "a" / "b" / "f.py").write_text("x=1\n", encoding="utf-8")
    seen: list[str] = []
    scan_project_files(str(tmp_path) + "/", on_directory=seen.append)
    assert any(p.rstrip("/").endswith("/a/b") or p.endswith("a/b/") for p in seen)


def test_merge_project_defaults_migrates_tree_exclude() -> None:
    from codimension.utils.project import merge_project_defaults

    props = merge_project_defaults({"excludeFromAnalysis": ["workbench"], "uuid": ""})
    assert props["excludeFromProjectTree"] == ["workbench"]
    assert props["slowScanPromptSeen"] == []


def test_slow_scan_timeout_applies_hot_dir(tmp_path: Path, monkeypatch) -> None:
    """``__onSlowScanTimeout`` persists the hot directory and requests a rescan."""
    pytest.importorskip("PyQt5")
    from PyQt5.QtWidgets import QApplication, QDialog

    _purge_stub_ui_for_project()
    sys.modules.pop("utils.project", None)
    sys.modules.pop("codimension.utils.project", None)

    from codimension.utils.project import CodimensionProject, merge_project_defaults

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    hot = tmp_path / "workbench" / "tools"
    hot.mkdir(parents=True)
    cdm = tmp_path / "demo.cdm3"
    uid = "00000000-0000-4000-8000-000000000099"
    cdm.write_text("{}", encoding="utf-8")

    class _Dlg:
        def __init__(self, relative_dir, parent=None):
            self.relative_dir = relative_dir

        def exec_(self):
            return QDialog.Accepted

        def selectedExcludes(self):
            return [self.relative_dir], [self.relative_dir]

    import ui.slowscanignoredlg as dlg_mod

    monkeypatch.setattr(dlg_mod, "SlowScanIgnoreDialog", _Dlg)

    rescans = {"n": 0}

    def _spy_generate(*_a, **_k):
        rescans["n"] += 1

    project = CodimensionProject()
    project.fileName = str(cdm)
    project.props = merge_project_defaults({"uuid": uid, "excludeFromAnalysis": []})
    project.filesList = {str(tmp_path) + "/"}
    fake_thread = MagicMock()
    fake_thread.isRunning.return_value = True
    fake_thread.hotDirectory.return_value = str(hot) + "/"
    project._CodimensionProject__scanThread = fake_thread  # noqa: SLF001
    monkeypatch.setattr(project, "_CodimensionProject__generateFilesList", _spy_generate)

    project._CodimensionProject__onSlowScanTimeout()  # noqa: SLF001

    assert "workbench/tools" in project.props["excludeFromAnalysis"]
    assert "workbench/tools" in project.props["excludeFromProjectTree"]
    assert "workbench/tools" in project.props["slowScanPromptSeen"]
    assert rescans["n"] == 1


def test_slow_scan_timeout_continue_rearms(tmp_path: Path, monkeypatch) -> None:
    """Continue scanning records the hot dir and rearms the timer."""
    pytest.importorskip("PyQt5")
    from PyQt5.QtWidgets import QApplication, QDialog

    _purge_stub_ui_for_project()
    sys.modules.pop("utils.project", None)
    sys.modules.pop("codimension.utils.project", None)

    from codimension.utils.project import CodimensionProject, merge_project_defaults

    if QApplication.instance() is None:
        QApplication([])

    hot = tmp_path / "workbench" / "tools"
    hot.mkdir(parents=True)
    cdm = tmp_path / "demo.cdm3"
    cdm.write_text("{}", encoding="utf-8")

    class _Dlg:
        def __init__(self, relative_dir, parent=None):
            pass

        def exec_(self):
            return QDialog.Rejected

        def selectedExcludes(self):
            return [], []

    import ui.slowscanignoredlg as dlg_mod

    monkeypatch.setattr(dlg_mod, "SlowScanIgnoreDialog", _Dlg)

    armed = {"n": 0}

    def _spy_arm(_self=None):
        armed["n"] += 1

    project = CodimensionProject()
    project.fileName = str(cdm)
    project.props = merge_project_defaults({"uuid": "00000000-0000-4000-8000-000000000088", "excludeFromAnalysis": []})
    fake_thread = MagicMock()
    fake_thread.isRunning.return_value = True
    fake_thread.hotDirectory.return_value = str(hot) + "/"
    project._CodimensionProject__scanThread = fake_thread  # noqa: SLF001
    monkeypatch.setattr(project, "_CodimensionProject__armSlowScanTimer", _spy_arm)
    monkeypatch.setattr(project, "_CodimensionProject__generateFilesList", lambda *a, **k: None)

    project._CodimensionProject__onSlowScanTimeout()  # noqa: SLF001
    assert project.props["excludeFromAnalysis"] == []
    assert "workbench/tools" in project.props["slowScanPromptSeen"]
    assert armed["n"] == 1


def test_update_properties_preserves_slow_scan_seen(tmp_path: Path, monkeypatch) -> None:
    """Properties dialog updates must not wipe slowScanPromptSeen."""
    pytest.importorskip("PyQt5")
    _purge_stub_ui_for_project()
    sys.modules.pop("utils.project", None)
    sys.modules.pop("codimension.utils.project", None)

    from codimension.utils.project import CodimensionProject, merge_project_defaults

    uid = "00000000-0000-4000-8000-000000000077"
    cdm = tmp_path / "demo.cdm3"
    props = merge_project_defaults(
        {
            "uuid": uid,
            "excludeFromAnalysis": [],
            "slowScanPromptSeen": ["workbench/tools"],
        }
    )
    cdm.write_text("{}", encoding="utf-8")
    project = CodimensionProject()
    project.fileName = str(cdm)
    project.props = props
    monkeypatch.setattr(project, "_CodimensionProject__generateFilesList", lambda *a, **k: None)

    updated = merge_project_defaults({"uuid": uid, "version": "9.9", "excludeFromAnalysis": []})
    del updated["slowScanPromptSeen"]
    project.updateProperties(updated)
    assert project.props["slowScanPromptSeen"] == ["workbench/tools"]
    assert project.props["version"] == "9.9"


def test_slow_scan_threshold_constant() -> None:
    assert SLOW_SCAN_PROMPT_MS == 30_000
