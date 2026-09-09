# -*- coding: utf-8 -*-
"""R265: full project lifecycle transaction — unload inside rollback boundary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.services import ApplicationServices


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
        self.fail_unload = False
        self.fail_unload_after_n = 0
        self._unload_attempts = 0

    def isLoaded(self) -> bool:
        return self.loaded

    def unloadProject(self, emitSignal: bool = True) -> None:
        del emitSignal
        self._unload_attempts += 1
        if self.fail_unload and self._unload_attempts > self.fail_unload_after_n:
            raise RuntimeError("simulated unload failure")
        self.unloads += 1
        self.loaded = False
        self.path = ""

    def loadProject(self, projectFile: str) -> None:
        if self.fail_load_for is not None and projectFile == self.fail_load_for:
            # Leave a partial loaded state to force abandon/restore paths.
            self.loaded = True
            self.path = projectFile
            raise RuntimeError(f"simulated load failure for {projectFile}")
        self.loads.append(projectFile)
        self.loaded = True
        self.path = projectFile

    def createNew(self, fileName: str, props) -> None:
        del props
        self.loads.append(fileName)
        self.loaded = True
        self.path = fileName


def test_r265_before_unload_failure_reattaches_previous(tmp_path: Path) -> None:
    """Detach hook failure must not leave the previous project without after_load."""
    old = _minimal_cdm3(tmp_path / "old.cdm3", uuid="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    new = _minimal_cdm3(tmp_path / "new.cdm3", uuid="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
    project = _FakeProject()
    hooks: list[str] = []
    boom = {"armed": False}

    def before_unload() -> None:
        hooks.append("detach")
        if boom["armed"]:
            raise RuntimeError("detach exploded")

    services = ApplicationServices(
        project,
        prevalidate=True,
        before_unload=before_unload,
        after_load=lambda p: hooks.append(f"after:{Path(p).name}"),
    )
    assert services.load_project(str(old)) is True
    boom["armed"] = True
    with pytest.raises(RuntimeError, match="detach exploded"):
        services.switch_project(str(new))

    assert project.loaded is True
    assert project.path == str(old)
    assert project.unloads == 0
    # Reattach after failed detach attempt.
    assert hooks.count(f"after:{old.name}") >= 2


def test_r265_unload_port_failure_restores_previous(tmp_path: Path) -> None:
    """If unloadProject fails after detach, previous project is restored/reattached."""
    old = _minimal_cdm3(tmp_path / "old.cdm3", uuid="cccccccc-cccc-4ccc-8ccc-cccccccccccc")
    new = _minimal_cdm3(tmp_path / "new.cdm3", uuid="dddddddd-dddd-4ddd-8ddd-dddddddddddd")
    project = _FakeProject()
    hooks: list[str] = []

    def before_unload() -> None:
        hooks.append("detach")
        # Simulate detach succeeding while port unload will fail.
        project.fail_unload = True

    services = ApplicationServices(
        project,
        prevalidate=True,
        before_unload=before_unload,
        after_load=lambda p: hooks.append(f"after:{Path(p).name}"),
    )
    assert services.load_project(str(old)) is True
    # First unload was during initial load? No - first load had nothing loaded.
    project.fail_unload = False
    # Arm failure only for the switch unload.
    with pytest.raises(RuntimeError, match="simulated unload failure"):
        # before_unload sets fail_unload True
        services.switch_project(str(new))

    assert project.loaded is True
    assert project.path == str(old)
    assert f"after:{old.name}" in hooks
    assert hooks.count(f"after:{old.name}") >= 2


def test_r265_no_previous_load_failure_abandons_partial(tmp_path: Path) -> None:
    """Without a previous project, a failed load must not leave a partial loaded port."""
    new = _minimal_cdm3(tmp_path / "new.cdm3", uuid="eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
    project = _FakeProject()
    hooks: list[str] = []
    project.fail_load_for = str(new)
    services = ApplicationServices(
        project,
        prevalidate=True,
        before_unload=lambda: hooks.append("detach"),
        after_unload=lambda: hooks.append("after_unload"),
        after_load=lambda p: hooks.append(f"after:{Path(p).name}"),
    )
    with pytest.raises(RuntimeError, match="simulated load failure"):
        services.load_project(str(new))

    assert project.loaded is False
    assert project.path == ""
    assert "detach" in hooks
    assert "after_unload" in hooks
    assert not any(h.startswith("after:") for h in hooks)


def test_r265_after_unload_failure_still_rollbacks_on_load_error(tmp_path: Path) -> None:
    """after_unload exception is inside the transaction and triggers restore."""
    old = _minimal_cdm3(tmp_path / "old.cdm3", uuid="ffffffff-ffff-4fff-8fff-ffffffffffff")
    new = _minimal_cdm3(tmp_path / "new.cdm3", uuid="12121212-1212-4121-8121-121212121212")
    project = _FakeProject()
    hooks: list[str] = []

    def after_unload() -> None:
        hooks.append("after_unload")
        raise RuntimeError("after_unload exploded")

    services = ApplicationServices(
        project,
        prevalidate=True,
        before_unload=lambda: hooks.append("detach"),
        after_unload=after_unload,
        after_load=lambda p: hooks.append(f"after:{Path(p).name}"),
    )
    assert services.load_project(str(old)) is True
    with pytest.raises(RuntimeError, match="after_unload exploded"):
        services.switch_project(str(new))

    assert project.loaded is True
    assert project.path == str(old)
    assert hooks.count(f"after:{old.name}") >= 2
