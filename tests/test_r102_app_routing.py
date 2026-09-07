# -*- coding: utf-8 -*-
"""R102 / R236: UI / startup project lifecycle must go through ApplicationServices."""

from __future__ import annotations

import ast
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_CODIM = _ROOT / "codimension"

# Call sites that must route via appServices (not project.load/unload/create directly).
_ROUTED_SOURCES = [
    _CODIM / "codimension.py",
    _CODIM / "ui" / "mainwindow.py",
    _CODIM / "ui" / "mainmenu.py",
    _CODIM / "ui" / "projectviewer.py",
    _CODIM / "ui" / "recentprojectsviewer.py",
]


def _forbidden_direct_project_calls(text: str) -> list[str]:
    """Return matches of project.load/unload/create outside comments."""
    hits: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if re.search(r"\.project\.loadProject\s*\(", line):
            hits.append(f"{lineno}: direct project.loadProject")
        if re.search(r"\.project\.unloadProject\s*\(", line):
            hits.append(f"{lineno}: direct project.unloadProject")
        if re.search(r"\.project\.createNew\s*\(", line):
            hits.append(f"{lineno}: direct project.createNew")
        if re.search(r"\bprj\.loadProject\s*\(", line):
            hits.append(f"{lineno}: direct prj.loadProject")
        if re.search(r"\bprj\.unloadProject\s*\(", line):
            hits.append(f"{lineno}: direct prj.unloadProject")
        if re.search(r"\bprj\.createNew\s*\(", line):
            hits.append(f"{lineno}: direct prj.createNew")
        if re.search(r"\bproject\.unloadProject\s*\(", line) and "appServices" not in line:
            hits.append(f"{lineno}: direct project.unloadProject")
        if re.search(r"\bproject\.createNew\s*\(", line) and "appServices" not in line:
            hits.append(f"{lineno}: direct project.createNew")
    return hits


def test_r102_routed_sources_use_app_services() -> None:
    """UI/startup files call appServices lifecycle APIs, not project port."""
    for path in _ROUTED_SOURCES:
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(_ROOT)
        has_lifecycle = any(
            token in text
            for token in (
                "appServices.load_project",
                "appServices.unload_project",
                "appServices.switch_project",
                "appServices.create_project",
            )
        )
        assert has_lifecycle, f"{rel}: missing appServices lifecycle call"
        forbidden = _forbidden_direct_project_calls(text)
        assert not forbidden, f"{rel}: {forbidden}"


def test_r236_create_project_routed_from_ui() -> None:
    """Create-project UI must use appServices.create_project (not createNew)."""
    for rel in ("ui/mainwindow.py", "ui/mainmenu.py"):
        text = (_CODIM / rel).read_text(encoding="utf-8")
        assert "appServices.create_project" in text, rel
        assert not re.search(r"\.project\.createNew\s*\(", text), rel


def test_r102_globals_wires_application_services() -> None:
    """GlobalDataWrapper constructs ApplicationServices over the project port."""
    text = (_CODIM / "utils" / "globals.py").read_text(encoding="utf-8")
    assert "from app.services import ApplicationServices" in text
    assert "self.appServices = ApplicationServices(" in text
    assert "self.project" in text


def test_r102_services_still_owns_project_port_calls() -> None:
    """Only the façade may call ProjectPort load/unload/create."""
    tree = ast.parse((_CODIM / "app" / "services.py").read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"loadProject", "unloadProject", "createNew"}
    ]
    assert len(calls) >= 3
    attrs = {node.func.attr for node in calls}
    assert attrs == {"loadProject", "unloadProject", "createNew"}
