# -*- coding: utf-8 -*-
"""R101 / R236: ApplicationServices façade — headless, injectable project port."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

from codimension.app import ApplicationServices
from codimension.app.services import ApplicationServices as ApplicationServicesDirect


class _FakeProject:
    """In-memory project port for façade unit tests."""

    def __init__(self) -> None:
        self.loaded_path: str | None = None
        self.load_calls: list[str] = []
        self.unload_calls: list[bool] = []
        self.create_calls: list[tuple[str, Mapping[str, Any]]] = []

    def loadProject(self, projectFile: str) -> None:
        self.load_calls.append(projectFile)
        self.loaded_path = projectFile

    def unloadProject(self, emitSignal: bool = True) -> None:
        self.unload_calls.append(emitSignal)
        self.loaded_path = None

    def createNew(self, fileName: str, props: Mapping[str, Any]) -> None:
        self.create_calls.append((fileName, props))
        self.loaded_path = fileName

    def isLoaded(self) -> bool:
        return self.loaded_path is not None


def test_application_services_load_unload_with_hooks() -> None:
    """Façade sequences hooks around the project port."""
    project = _FakeProject()
    events: list[str] = []

    services = ApplicationServices(
        project,
        before_load=lambda path: events.append(f"before:{path}") or True,
        after_load=lambda path: events.append(f"after:{path}"),
        before_unload=lambda: events.append("before_unload"),
        after_unload=lambda: events.append("after_unload"),
    )

    assert services.project_loaded is False
    assert services.load_project("/tmp/demo.cdm3") is True
    assert project.load_calls == ["/tmp/demo.cdm3"]
    assert services.project_loaded is True
    assert events == ["before:/tmp/demo.cdm3", "after:/tmp/demo.cdm3"]

    services.unload_project(emit_signal=False)
    assert project.unload_calls == [False]
    assert services.project_loaded is False
    assert events[-2:] == ["before_unload", "after_unload"]


def test_application_services_before_load_can_abort() -> None:
    """Returning False from before_load skips loadProject."""
    project = _FakeProject()
    services = ApplicationServices(project, before_load=lambda _path: False)
    assert services.load_project("/tmp/nope.cdm3") is False
    assert project.load_calls == []
    assert services.project_loaded is False


def test_application_services_package_export() -> None:
    """Package lazy export matches direct import."""
    assert ApplicationServices is ApplicationServicesDirect


def test_r236_load_over_existing_unloads_first() -> None:
    """R236: switching via load_project runs before_unload then after_load."""
    project = _FakeProject()
    events: list[str] = []
    services = ApplicationServices(
        project,
        after_load=lambda path: events.append(f"after:{path}"),
        before_unload=lambda: events.append("before_unload"),
        after_unload=lambda: events.append("after_unload"),
    )
    assert services.load_project("/tmp/a.cdm3") is True
    assert services.switch_project("/tmp/b.cdm3") is True
    assert project.unload_calls == [True]
    assert project.load_calls == ["/tmp/a.cdm3", "/tmp/b.cdm3"]
    assert project.loaded_path == "/tmp/b.cdm3"
    assert events == [
        "after:/tmp/a.cdm3",
        "before_unload",
        "after_unload",
        "after:/tmp/b.cdm3",
    ]


def test_r236_create_project_runs_lifecycle_hooks() -> None:
    """R236: create_project detaches old workspace and attaches the new one."""
    project = _FakeProject()
    events: list[str] = []
    services = ApplicationServices(
        project,
        after_load=lambda path: events.append(f"after:{path}"),
        before_unload=lambda: events.append("before_unload"),
    )
    assert services.load_project("/tmp/old.cdm3") is True
    props = {"author": "r236", "importdirs": ["."]}
    assert services.create_project("/tmp/new.cdm3", props) is True
    assert project.unload_calls == [True]
    assert len(project.create_calls) == 1
    assert project.create_calls[0][0] == "/tmp/new.cdm3"
    assert project.create_calls[0][1]["author"] == "r236"
    assert project.load_calls == ["/tmp/old.cdm3"]
    assert project.loaded_path == "/tmp/new.cdm3"
    assert events == ["after:/tmp/old.cdm3", "before_unload", "after:/tmp/new.cdm3"]


def test_r236_create_project_before_load_can_abort() -> None:
    project = _FakeProject()
    services = ApplicationServices(project, before_load=lambda _path: False)
    assert services.create_project("/tmp/x.cdm3", {}) is False
    assert project.create_calls == []


def test_r101_app_import_subprocess_without_qt() -> None:
    """Gate: importing codimension.app must not pull Qt."""
    root = Path(__file__).resolve().parents[1]
    code = (
        "import sys\n"
        f"sys.path.insert(0, {str(root)!r})\n"
        "assert 'PyQt5' not in sys.modules\n"
        "from codimension.app import ApplicationServices\n"
        "class P:\n"
        "    def loadProject(self, projectFile): self.p = projectFile\n"
        "    def unloadProject(self, emitSignal=True): self.p = None\n"
        "    def createNew(self, fileName, props): self.p = fileName\n"
        "    def isLoaded(self): return getattr(self, 'p', None) is not None\n"
        "s = ApplicationServices(P())\n"
        "assert s.load_project('x.cdm3') is True\n"
        "assert s.project_loaded is True\n"
        "assert s.create_project('y.cdm3', {}) is True\n"
        "assert 'PyQt5' not in sys.modules\n"
        "assert 'ui.qt' not in sys.modules\n"
        "print('OK')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(root),
    )
    assert proc.returncode == 0, proc.stderr
    assert "OK" in proc.stdout
