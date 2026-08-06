# -*- coding: utf-8 -*-
"""B09/B10/C05 — schema on all project update paths, atomic settings, uuid4 persist."""

from __future__ import annotations

import json
import os
import stat
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def project_mod(monkeypatch, tmp_path):
    """Import project helpers with SETTINGS_DIR redirected under tmp_path."""
    settings_dir = tmp_path / "settings"
    settings_dir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))

    # Ensure package imports resolve
    import sys

    sys.path.insert(0, str(ROOT / "codimension"))
    sys.path.insert(0, str(ROOT))

    import utils.project as project
    import utils.settings as settings_mod

    monkeypatch.setattr(settings_mod, "SETTINGS_DIR", str(settings_dir) + os.sep)
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
        "encoding": "",
        "pythoninterpreter": "",
    }
    props.update(overrides)
    return props


def test_atomic_preserves_mode_and_dir_fsync(tmp_path, monkeypatch):
    from utils.atomic_io import atomic_write_text

    path = tmp_path / "cfg.json"
    path.write_text("old\n", encoding="utf-8")
    os.chmod(path, 0o640)
    fsynced = []

    real_fsync = os.fsync

    def _spy_fsync(fd):
        fsynced.append(fd)
        return real_fsync(fd)

    monkeypatch.setattr(os, "fsync", _spy_fsync)
    atomic_write_text(str(path), "new\n")
    assert path.read_text(encoding="utf-8") == "new\n"
    assert stat.S_IMODE(path.stat().st_mode) == 0o640
    assert len(fsynced) >= 2  # file + directory


def test_new_project_uuid_is_uuid4(project_mod):
    project, _ = project_mod
    value = project.new_project_uuid()
    parsed = uuid.UUID(value)
    assert parsed.version == 4


def test_get_project_properties_rejects_bad_json(project_mod, tmp_path):
    project, _ = project_mod
    path = tmp_path / "bad.cdm3"
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(Exception, match="Bad project file"):
        project.getProjectProperties(str(path))


def test_get_project_properties_rejects_schema(project_mod, tmp_path):
    project, _ = project_mod
    path = tmp_path / "bad.cdm3"
    path.write_text(json.dumps({"uuid": 123}), encoding="utf-8")
    with pytest.raises(Exception, match="Bad project file"):
        project.getProjectProperties(str(path))


def test_update_properties_validates(project_mod, tmp_path):
    project, settings_dir = project_mod
    proj = project.CodimensionProject()
    cdm = tmp_path / "demo.cdm3"
    uid = str(uuid.uuid4())
    props = _minimal_props(uuid=uid, version="1.0")
    cdm.write_text(json.dumps(props), encoding="utf-8")
    proj.fileName = str(cdm)
    proj.props = props
    proj.userProjectDir = str(settings_dir / uid) + os.sep
    os.makedirs(proj.userProjectDir, exist_ok=True)

    with pytest.raises(project.ProjectSchemaError):
        proj.updateProperties({"uuid": "not-a-uuid", "importdirs": []})
    assert proj.props["version"] == "1.0"

    updated = _minimal_props(uuid=uid, version="2.0")
    proj.updateProperties(updated)
    assert proj.props["version"] == "2.0"
    disk = json.loads(cdm.read_text(encoding="utf-8"))
    assert disk["version"] == "2.0"


def test_on_project_file_updated_keeps_last_known_good(project_mod, tmp_path):
    project, settings_dir = project_mod
    proj = project.CodimensionProject()
    cdm = tmp_path / "demo.cdm3"
    uid = str(uuid.uuid4())
    props = _minimal_props(uuid=uid, version="keep-me")
    cdm.write_text(json.dumps(props), encoding="utf-8")
    proj.fileName = str(cdm)
    proj.props = dict(props)
    proj.userProjectDir = str(settings_dir / uid) + os.sep

    cdm.write_text("{broken", encoding="utf-8")
    proj.onProjectFileUpdated()
    assert proj.props["version"] == "keep-me"


def test_uuid_migration_persists_immediately(project_mod, tmp_path, monkeypatch):
    project, _ = project_mod
    cdm = tmp_path / "legacy.cdm3"
    props = _minimal_props(uuid="")
    cdm.write_text(json.dumps(props), encoding="utf-8")

    proj = project.CodimensionProject()
    monkeypatch.setattr(proj, "_CodimensionProject__generateFilesList", lambda *a, **k: None)
    proj.loadProject(str(cdm))
    disk = json.loads(cdm.read_text(encoding="utf-8"))
    assert disk["uuid"]
    assert uuid.UUID(disk["uuid"]).version == 4
    assert proj.props["uuid"] == disk["uuid"]


def test_settings_flush_atomic(tmp_path, monkeypatch):
    """Settings.flush must go through atomic_write_text (B10)."""
    import utils.settings as settings_mod

    calls = []

    def _spy(path, content, *, encoding="utf-8", mode=None):
        calls.append(path)
        Path(path).write_text(content, encoding=encoding)

    monkeypatch.setattr(settings_mod, "atomic_write_text", _spy)
    wrapper = settings_mod.SettingsWrapper.__new__(settings_mod.SettingsWrapper)
    wrapper._SettingsWrapper__values = {"x": 1}  # noqa: SLF001
    wrapper._SettingsWrapper__fullFileName = str(tmp_path / "settings.json")  # noqa: SLF001
    settings_mod.SettingsWrapper.flush(wrapper)
    assert calls and calls[0].endswith("settings.json")
    assert (tmp_path / "settings.json").exists()
