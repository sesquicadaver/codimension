# -*- coding: utf-8 -*-
"""R257: transactional project switch — prevalidate + rollback previous."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.services import (
    ApplicationServices,
    current_project_path,
    default_prevalidate_project_create_target,
    default_prevalidate_project_load_target,
)


def _minimal_cdm3(path: Path, *, uuid: str = "11111111-1111-4111-8111-111111111111") -> Path:
    payload = {
        "scriptname": "",
        "mddocfile": "",
        "creationdate": "",
        "author": "",
        "license": "",
        "copyright": "",
        "version": "1.0",
        "email": "",
        "description": "",
        "uuid": uuid,
        "importdirs": [],
        "excludeFromAnalysis": [],
        "excludeFromProjectTree": [],
        "slowScanPromptSeen": [],
        "encoding": "",
        "pythoninterpreter": "",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class _FakeProject:
    def __init__(self) -> None:
        self.loaded = False
        self.path = ""
        self.unloads = 0
        self.loads: list[str] = []
        self.fail_load_for: str | None = None
        self.fail_create = False

    def isLoaded(self) -> bool:
        return self.loaded

    def unloadProject(self, emitSignal: bool = True) -> None:
        del emitSignal
        self.unloads += 1
        self.loaded = False
        self.path = ""

    def loadProject(self, projectFile: str) -> None:
        if self.fail_load_for is not None and projectFile == self.fail_load_for:
            raise RuntimeError(f"simulated load failure for {projectFile}")
        self.loads.append(projectFile)
        self.loaded = True
        self.path = projectFile

    def createNew(self, fileName: str, props) -> None:
        del props
        if self.fail_create:
            raise RuntimeError("simulated create failure")
        self.loads.append(fileName)
        self.loaded = True
        self.path = fileName


def test_r257_prevalidate_rejects_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "nope.cdm3"
    with pytest.raises(FileNotFoundError):
        default_prevalidate_project_load_target(str(missing))


def test_r257_prevalidate_rejects_bad_json(tmp_path: Path) -> None:
    bad = tmp_path / "bad.cdm3"
    bad.write_text("not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="readable JSON"):
        default_prevalidate_project_load_target(str(bad))


def test_r257_prevalidate_accepts_minimal_object(tmp_path: Path) -> None:
    ok = _minimal_cdm3(tmp_path / "ok.cdm3")
    default_prevalidate_project_load_target(str(ok))


def test_r257_load_failure_restores_previous_project(tmp_path: Path) -> None:
    old = _minimal_cdm3(tmp_path / "old.cdm3", uuid="22222222-2222-4222-8222-222222222222")
    new = _minimal_cdm3(tmp_path / "new.cdm3", uuid="33333333-3333-4333-8333-333333333333")
    project = _FakeProject()
    hooks: list[str] = []
    services = ApplicationServices(
        project,
        prevalidate=True,
        after_load=lambda p: hooks.append(f"after:{Path(p).name}"),
        before_unload=lambda: hooks.append("detach"),
    )
    assert services.load_project(str(old)) is True
    assert project.path == str(old)

    project.fail_load_for = str(new)
    with pytest.raises(RuntimeError, match="simulated load failure"):
        services.switch_project(str(new))

    assert project.loaded is True
    assert project.path == str(old)
    assert project.unloads >= 1
    assert f"after:{old.name}" in hooks
    # Restore re-ran after_load for the previous project.
    assert hooks.count(f"after:{old.name}") >= 2


def test_r257_after_load_failure_restores_previous(tmp_path: Path) -> None:
    old = _minimal_cdm3(tmp_path / "old.cdm3", uuid="44444444-4444-4444-8444-444444444444")
    new = _minimal_cdm3(tmp_path / "new.cdm3", uuid="55555555-5555-4555-8555-555555555555")
    project = _FakeProject()
    boom = {"n": 0}

    def after(path: str) -> None:
        boom["n"] += 1
        if Path(path).name == "new.cdm3":
            raise RuntimeError("after_load exploded")

    services = ApplicationServices(project, prevalidate=True, after_load=after)
    assert services.load_project(str(old)) is True
    with pytest.raises(RuntimeError, match="after_load exploded"):
        services.switch_project(str(new))
    assert project.path == str(old)
    assert project.loaded is True


def test_r257_invalid_target_does_not_unload(tmp_path: Path) -> None:
    old = _minimal_cdm3(tmp_path / "old.cdm3", uuid="66666666-6666-4666-8666-666666666666")
    project = _FakeProject()
    services = ApplicationServices(project, prevalidate=True)
    assert services.load_project(str(old)) is True
    with pytest.raises(FileNotFoundError):
        services.switch_project(str(tmp_path / "missing.cdm3"))
    assert project.unloads == 0
    assert project.path == str(old)


def test_r257_create_failure_restores_previous(tmp_path: Path) -> None:
    old = _minimal_cdm3(tmp_path / "old.cdm3", uuid="77777777-7777-4777-8777-777777777777")
    project = _FakeProject()
    services = ApplicationServices(project, prevalidate=True)
    assert services.load_project(str(old)) is True
    project.fail_create = True
    target = tmp_path / "brand.cdm3"
    with pytest.raises(RuntimeError, match="simulated create"):
        services.create_project(str(target), {"author": "r257"})
    assert project.path == str(old)
    assert project.loaded is True


def test_r257_create_prevalidate_parent(tmp_path: Path) -> None:
    missing_parent = tmp_path / "nope" / "x.cdm3"
    with pytest.raises(FileNotFoundError):
        default_prevalidate_project_create_target(str(missing_parent), {})


def test_r257_current_project_path_prefers_fileName() -> None:
    class P:
        fileName = "/a.cdm3"
        path = "/b.cdm3"

        def loadProject(self, projectFile: str) -> None:
            return None

        def unloadProject(self, emitSignal: bool = True) -> None:
            return None

        def createNew(self, fileName: str, props) -> None:
            return None

        def isLoaded(self) -> bool:
            return True

    assert current_project_path(P()) == "/a.cdm3"
