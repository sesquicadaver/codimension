# -*- coding: utf-8 -*-
"""R102: UI / startup project load+unload must go through ApplicationServices."""

from __future__ import annotations

import ast
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_CODIM = _ROOT / "codimension"

# Call sites that must route via appServices (not project.load/unload directly).
_ROUTED_SOURCES = [
    _CODIM / "codimension.py",
    _CODIM / "ui" / "mainwindow.py",
    _CODIM / "ui" / "projectviewer.py",
    _CODIM / "ui" / "recentprojectsviewer.py",
]


def _forbidden_direct_project_calls(text: str) -> list[str]:
    """Return matches of project.loadProject / project.unloadProject outside comments."""
    hits: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if re.search(r"\.project\.loadProject\s*\(", line):
            hits.append(f"{lineno}: direct project.loadProject")
        if re.search(r"\.project\.unloadProject\s*\(", line):
            hits.append(f"{lineno}: direct project.unloadProject")
        # local alias: prj.loadProject / project.unloadProject(False) after assignment
        if re.search(r"\bprj\.loadProject\s*\(", line):
            hits.append(f"{lineno}: direct prj.loadProject")
        if re.search(r"\bprj\.unloadProject\s*\(", line):
            hits.append(f"{lineno}: direct prj.unloadProject")
        if re.search(r"\bproject\.unloadProject\s*\(", line) and "appServices" not in line:
            hits.append(f"{lineno}: direct project.unloadProject")
    return hits


def test_r102_routed_sources_use_app_services() -> None:
    """UI/startup files call appServices.load/unload_project, not project port."""
    for path in _ROUTED_SOURCES:
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(_ROOT)
        assert "appServices.load_project" in text or "appServices.unload_project" in text, (
            f"{rel}: missing appServices load/unload call"
        )
        forbidden = _forbidden_direct_project_calls(text)
        assert not forbidden, f"{rel}: {forbidden}"


def test_r102_globals_wires_application_services() -> None:
    """GlobalDataWrapper constructs ApplicationServices over the project port."""
    text = (_CODIM / "utils" / "globals.py").read_text(encoding="utf-8")
    assert "from app.services import ApplicationServices" in text
    assert "self.appServices = ApplicationServices(self.project)" in text


def test_r102_services_still_owns_project_port_calls() -> None:
    """Only the façade may call ProjectPort.loadProject/unloadProject."""
    tree = ast.parse((_CODIM / "app" / "services.py").read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"loadProject", "unloadProject"}
    ]
    assert len(calls) >= 2
