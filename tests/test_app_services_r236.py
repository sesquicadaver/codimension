# -*- coding: utf-8 -*-
"""R236: project create/switch lifecycle via ApplicationServices."""

from __future__ import annotations

from pathlib import Path

from codimension.app.services import ApplicationServices


class _TrackingProject:
    """Minimal port that records lifecycle order."""

    def __init__(self) -> None:
        self.path = ""
        self.events: list[str] = []

    def isLoaded(self) -> bool:
        return bool(self.path)

    def unloadProject(self, emitSignal: bool = True) -> None:
        self.events.append(f"unload:{emitSignal}")
        self.path = ""

    def loadProject(self, projectFile: str) -> None:
        self.events.append(f"load:{projectFile}")
        self.path = projectFile

    def createNew(self, fileName: str, props: dict) -> None:
        self.events.append(f"create:{fileName}:{props.get('author', '')}")
        self.path = fileName


def test_r236_create_over_loaded_detaches_then_attaches() -> None:
    project = _TrackingProject()
    hooks: list[str] = []
    services = ApplicationServices(
        project,
        after_load=lambda path: hooks.append(f"attach:{Path(path).name}"),
        before_unload=lambda: hooks.append("detach"),
    )
    assert services.load_project("/ws/a.cdm3")
    assert services.create_project("/ws/b.cdm3", {"author": "r236"})
    assert hooks == ["attach:a.cdm3", "detach", "attach:b.cdm3"]
    assert project.events == [
        "load:/ws/a.cdm3",
        "unload:True",
        "create:/ws/b.cdm3:r236",
    ]
    assert services.project_loaded is True


def test_r236_switch_project_is_unload_then_load() -> None:
    project = _TrackingProject()
    hooks: list[str] = []
    services = ApplicationServices(
        project,
        after_load=lambda path: hooks.append(f"attach:{Path(path).name}"),
        before_unload=lambda: hooks.append("detach"),
    )
    assert services.load_project("/ws/one.cdm3")
    assert services.switch_project("/ws/two.cdm3")
    assert hooks == ["attach:one.cdm3", "detach", "attach:two.cdm3"]
    assert project.path == "/ws/two.cdm3"
