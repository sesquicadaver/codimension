# -*- coding: utf-8 -*-
"""Slow-scan ignore prompt helpers and project integration."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from codimension.utils.slow_scan_prompt import (
    SLOW_SCAN_PROMPT_MS,
    filter_unseen_dir_names,
    list_top_level_dir_names,
    merge_prompt_seen,
    merge_unique_paths,
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


def test_list_top_level_dir_names(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "workbench").mkdir()
    (tmp_path / "file.py").write_text("x=1\n", encoding="utf-8")
    (tmp_path / ".hidden").mkdir()
    names = list_top_level_dir_names(str(tmp_path), should_exclude_name=lambda n: n.startswith("."))
    assert names == ["src", "workbench"]


def test_filter_unseen_and_merge() -> None:
    assert filter_unseen_dir_names(["a", "b", "c"], ["b"]) == ["a", "c"]
    assert merge_unique_paths(["a"], ["a", "b", "  "]) == ["a", "b"]
    assert merge_prompt_seen(["a"], ["b", "a"]) == ["a", "b"]


def test_merge_project_defaults_migrates_tree_exclude() -> None:
    from codimension.utils.project import merge_project_defaults

    props = merge_project_defaults({"excludeFromAnalysis": ["workbench"], "uuid": ""})
    assert props["excludeFromProjectTree"] == ["workbench"]
    assert props["slowScanPromptSeen"] == []


def test_merge_project_defaults_keeps_explicit_tree_list() -> None:
    from codimension.utils.project import merge_project_defaults

    props = merge_project_defaults(
        {
            "excludeFromAnalysis": ["workbench"],
            "excludeFromProjectTree": [],
            "uuid": "",
        }
    )
    assert props["excludeFromProjectTree"] == []


def test_slow_scan_timeout_applies_excludes(tmp_path: Path, monkeypatch) -> None:
    """``__onSlowScanTimeout`` persists selections and requests a rescan."""
    pytest.importorskip("PyQt5")
    from PyQt5.QtWidgets import QApplication, QDialog

    _purge_stub_ui_for_project()
    sys.modules.pop("utils.project", None)
    sys.modules.pop("codimension.utils.project", None)

    from codimension.utils.project import CodimensionProject, merge_project_defaults

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    (tmp_path / "src").mkdir()
    (tmp_path / "workbench").mkdir()
    cdm = tmp_path / "demo.cdm3"
    uid = "00000000-0000-4000-8000-000000000099"
    cdm.write_text("{}", encoding="utf-8")

    class _Dlg:
        def __init__(self, offered, parent=None):
            self.offered = list(offered)

        def exec_(self):
            return QDialog.Accepted

        def selectedExcludes(self):
            return ["workbench"], ["workbench"]

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
    project._CodimensionProject__scanThread = fake_thread  # noqa: SLF001
    monkeypatch.setattr(project, "_CodimensionProject__generateFilesList", _spy_generate)

    project._CodimensionProject__onSlowScanTimeout()  # noqa: SLF001

    assert "workbench" in project.props["excludeFromAnalysis"]
    assert "workbench" in project.props["excludeFromProjectTree"]
    assert set(project.props["slowScanPromptSeen"]) >= {"src", "workbench"}
    assert rescans["n"] == 1
    disk = cdm.read_text(encoding="utf-8")
    assert "workbench" in disk


def test_slow_scan_timeout_continue_marks_seen(tmp_path: Path, monkeypatch) -> None:
    """Continue scanning records offered dirs without changing excludes."""
    pytest.importorskip("PyQt5")
    from PyQt5.QtWidgets import QApplication, QDialog

    _purge_stub_ui_for_project()
    sys.modules.pop("utils.project", None)
    sys.modules.pop("codimension.utils.project", None)

    from codimension.utils.project import CodimensionProject, merge_project_defaults

    if QApplication.instance() is None:
        QApplication([])

    (tmp_path / "workbench").mkdir()
    cdm = tmp_path / "demo.cdm3"
    cdm.write_text("{}", encoding="utf-8")

    class _Dlg:
        def __init__(self, offered, parent=None):
            pass

        def exec_(self):
            return QDialog.Rejected

        def selectedExcludes(self):
            return [], []

    import ui.slowscanignoredlg as dlg_mod

    monkeypatch.setattr(dlg_mod, "SlowScanIgnoreDialog", _Dlg)

    project = CodimensionProject()
    project.fileName = str(cdm)
    project.props = merge_project_defaults(
        {"uuid": "00000000-0000-4000-8000-000000000088", "excludeFromAnalysis": []}
    )
    fake_thread = MagicMock()
    fake_thread.isRunning.return_value = True
    project._CodimensionProject__scanThread = fake_thread  # noqa: SLF001
    monkeypatch.setattr(project, "_CodimensionProject__generateFilesList", lambda *a, **k: None)

    project._CodimensionProject__onSlowScanTimeout()  # noqa: SLF001
    assert project.props["excludeFromAnalysis"] == []
    assert "workbench" in project.props["slowScanPromptSeen"]


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
            "slowScanPromptSeen": ["workbench"],
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
    assert project.props["slowScanPromptSeen"] == ["workbench"]
    assert project.props["version"] == "9.9"


def test_slow_scan_threshold_constant() -> None:
    assert SLOW_SCAN_PROMPT_MS == 30_000
