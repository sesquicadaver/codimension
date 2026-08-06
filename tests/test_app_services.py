# -*- coding: utf-8 -*-
"""R101: ApplicationServices façade — headless, injectable project port."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from codimension.app import ApplicationServices
from codimension.app.services import ApplicationServices as ApplicationServicesDirect


class _FakeProject:
    """In-memory project port for façade unit tests."""

    def __init__(self) -> None:
        self.loaded_path: str | None = None
        self.load_calls: list[str] = []
        self.unload_calls: list[bool] = []

    def loadProject(self, projectFile: str) -> None:
        self.load_calls.append(projectFile)
        self.loaded_path = projectFile

    def unloadProject(self, emitSignal: bool = True) -> None:
        self.unload_calls.append(emitSignal)
        self.loaded_path = None

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
        "    def isLoaded(self): return getattr(self, 'p', None) is not None\n"
        "s = ApplicationServices(P())\n"
        "assert s.load_project('x.cdm3') is True\n"
        "assert s.project_loaded is True\n"
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
