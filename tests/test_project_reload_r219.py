# -*- coding: utf-8 -*-
"""R219 — project reload: immutable UUID + single diff/rebuild pipeline."""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _purge_incomplete_stubs(*prefixes: str) -> None:
    for name in list(sys.modules):
        if not any(name == p or name.startswith(p + ".") for p in prefixes):
            continue
        mod = sys.modules.get(name)
        if mod is None:
            continue
        file_name = (getattr(mod, "__file__", None) or "").replace("\\", "/")
        if "codimension/" not in file_name and "codimension\\" not in file_name:
            del sys.modules[name]


@pytest.fixture
def project_mod(monkeypatch, tmp_path):
    settings_dir = tmp_path / "settings"
    settings_dir.mkdir()
    _purge_incomplete_stubs("utils", "ui")
    import utils.project as project

    monkeypatch.setattr(project, "SETTINGS_DIR", str(settings_dir) + os.sep)
    monkeypatch.setattr(project, "Settings", MagicMock(return_value=MagicMock(addRecentProject=MagicMock())))
    return project, settings_dir


def _minimal_props(**overrides):
    props = {
        "scriptname": "",
        "mddocfile": "",
        "creationdate": "",
        "author": "",
        "license": "",
        "copyright": "",
        "version": "",
        "email": "",
        "description": "",
        "uuid": "",
        "importdirs": [],
        "excludeFromAnalysis": [],
        "excludeFromProjectTree": [],
        "slowScanPromptSeen": [],
        "encoding": "",
        "pythoninterpreter": "",
    }
    props.update(overrides)
    return props


def _loaded_project(project, settings_dir, tmp_path, **prop_overrides):
    proj = project.CodimensionProject()
    cdm = tmp_path / "demo.cdm3"
    uid = str(uuid.uuid4())
    props = _minimal_props(uuid=uid, **prop_overrides)
    cdm.write_text(json.dumps(props), encoding="utf-8")
    proj.fileName = str(cdm)
    proj.props = dict(props)
    proj.userProjectDir = str(settings_dir / uid) + os.sep
    os.makedirs(proj.userProjectDir, exist_ok=True)
    return proj, cdm, uid


def test_r219_update_properties_uses_rebuild_pipeline(project_mod, tmp_path, monkeypatch):
    project, settings_dir = project_mod
    proj, _cdm, uid = _loaded_project(project, settings_dir, tmp_path, importdirs=[])
    calls: list[dict] = []

    def _spy(*, reattach_venv=False):
        calls.append({"reattach_venv": reattach_venv, "user_dir": proj.userProjectDir})

    monkeypatch.setattr(proj, "_CodimensionProject__rebuildAfterPropertyChange", _spy)
    updated = _minimal_props(uuid=uid, importdirs=["lib"], version="1")
    proj.updateProperties(updated)
    assert len(calls) == 1
    assert calls[0]["reattach_venv"] is False
    assert calls[0]["user_dir"] == str(settings_dir / uid) + os.sep
    assert proj.props["importdirs"] == ["lib"]
    assert proj.userProjectDir == str(settings_dir / uid) + os.sep


def test_r219_interpreter_change_reattaches_venv(project_mod, tmp_path, monkeypatch):
    project, settings_dir = project_mod
    proj, _cdm, uid = _loaded_project(project, settings_dir, tmp_path, pythoninterpreter="")
    calls: list[dict] = []

    def _spy(*, reattach_venv=False):
        calls.append({"reattach_venv": reattach_venv})

    monkeypatch.setattr(proj, "_CodimensionProject__rebuildAfterPropertyChange", _spy)
    updated = _minimal_props(uuid=uid, pythoninterpreter="/usr/bin/python3")
    proj.updateProperties(updated)
    assert calls == [{"reattach_venv": True}]


def test_r219_tree_exclude_triggers_rebuild(project_mod, tmp_path, monkeypatch):
    project, settings_dir = project_mod
    proj, _cdm, uid = _loaded_project(project, settings_dir, tmp_path)
    calls: list[dict] = []
    monkeypatch.setattr(
        proj,
        "_CodimensionProject__rebuildAfterPropertyChange",
        lambda *, reattach_venv=False: calls.append(reattach_venv),
    )
    updated = _minimal_props(uuid=uid, excludeFromProjectTree=["vendor"])
    proj.updateProperties(updated)
    assert calls == [False]


def test_r219_external_reload_does_not_remount_user_dir(project_mod, tmp_path, monkeypatch):
    project, settings_dir = project_mod
    proj, cdm, uid = _loaded_project(project, settings_dir, tmp_path, importdirs=[])
    original_dir = proj.userProjectDir
    rebuilds = []

    def _spy(*, reattach_venv=False):
        rebuilds.append(reattach_venv)
        # Simulate what rebuild does — must not touch userProjectDir.
        assert proj.userProjectDir == original_dir

    monkeypatch.setattr(proj, "_CodimensionProject__rebuildAfterPropertyChange", _spy)
    disk = _minimal_props(uuid=uid, importdirs=["pkg"], version="ext")
    cdm.write_text(json.dumps(disk), encoding="utf-8")
    proj.onProjectFileUpdated()
    assert rebuilds == [False]
    assert proj.userProjectDir == original_dir
    assert proj.props["importdirs"] == ["pkg"]


def test_r219_refresh_analysis_uses_same_rebuild(project_mod, tmp_path, monkeypatch):
    project, settings_dir = project_mod
    proj, _cdm, _uid = _loaded_project(project, settings_dir, tmp_path)
    calls = []
    monkeypatch.setattr(
        proj,
        "_CodimensionProject__rebuildAfterPropertyChange",
        lambda *, reattach_venv=False: calls.append(reattach_venv),
    )
    proj.refreshAnalysisEnvironment()
    assert calls == [False]


def test_r219_set_import_dirs_routes_through_update_properties(project_mod, tmp_path, monkeypatch):
    project, settings_dir = project_mod
    proj, _cdm, _uid = _loaded_project(project, settings_dir, tmp_path, importdirs=[])
    calls = []

    def _spy(props, *, persist=True):
        calls.append({"importdirs": list(props.get("importdirs", [])), "persist": persist})
        proj.props = dict(props)

    monkeypatch.setattr(proj, "updateProperties", _spy)
    proj.setImportDirs(["extra"])
    assert len(calls) == 1
    assert calls[0]["importdirs"] == ["extra"]
    assert calls[0]["persist"] is True
