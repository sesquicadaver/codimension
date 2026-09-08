# -*- coding: utf-8 -*-
"""R251: residual P2 correctness (source-bind, switch, taint, plugin, URI)."""

from __future__ import annotations

import os
from pathlib import Path

from app.services import ApplicationServices
from core.ai_findings import AiFinding, AiFindingSeverity, validate_audit_finding
from core.taint import analyze_function_taint
from infrastructure.file_uri import path_to_file_uri
from infrastructure.lsp_process import _path_to_uri
from plugins.policy import capture_plugin_file_identity, validate_candidate_before_import


class _FakeProject:
    def __init__(self) -> None:
        self.loaded = False
        self.path = ""
        self.unloads = 0
        self.loads: list[str] = []

    def isLoaded(self) -> bool:
        return self.loaded

    def unloadProject(self, emitSignal: bool = True) -> None:
        self.unloads += 1
        self.loaded = False
        self.path = ""

    def loadProject(self, projectFile: str) -> None:
        self.loads.append(projectFile)
        self.loaded = True
        self.path = projectFile

    def createNew(self, fileName: str, props) -> None:
        self.loads.append(fileName)
        self.loaded = True
        self.path = fileName


def test_r251_ai_finding_rejects_other_project_file(tmp_path: Path) -> None:
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("def a():\n    return 'evidence-a'\n", encoding="utf-8")
    b.write_text("def b():\n    return 0\n", encoding="utf-8")
    finding = AiFinding(
        finding_id="x",
        severity=AiFindingSeverity.INFO,
        confidence=0.9,
        title="cross",
        message="m",
        file_path=str(b),
        begin_line=1,
        end_line=1,
        evidence="evidence-a",
    )
    assert (
        validate_audit_finding(
            finding,
            source=a.read_text(encoding="utf-8"),
            default_file=str(a),
            project_dir=str(tmp_path),
            project_files=(str(a), str(b)),
        )
        is None
    )
    ok = AiFinding(
        finding_id="y",
        severity=AiFindingSeverity.INFO,
        confidence=0.9,
        title="same",
        message="m",
        file_path=str(a),
        begin_line=2,
        end_line=2,
        evidence="evidence-a",
    )
    assert (
        validate_audit_finding(
            ok,
            source=a.read_text(encoding="utf-8"),
            default_file=str(a),
            project_dir=str(tmp_path),
            project_files=(str(a), str(b)),
        )
        is not None
    )


def test_r251_before_load_abort_keeps_previous_project() -> None:
    project = _FakeProject()
    project.loaded = True
    project.path = "/old.cdm3"
    services = ApplicationServices(project, before_load=lambda _p: False)
    assert services.load_project("/new.cdm3") is False
    assert project.unloads == 0
    assert project.loaded is True
    assert project.path == "/old.cdm3"
    assert services.create_project("/new2.cdm3", {}) is False
    assert project.unloads == 0
    assert project.loaded is True


def test_r251_taint_skips_code_after_return() -> None:
    src = """
def f(x):
    return x
    eval(x)
"""
    report = analyze_function_taint(src, function="f")
    assert report.findings == ()


def test_r251_taint_skips_code_after_break() -> None:
    src = """
def f(x):
    while True:
        break
        eval(x)
"""
    report = analyze_function_taint(src, function="f")
    assert report.findings == ()


def test_r251_plugin_package_sibling_changes_identity(tmp_path: Path) -> None:
    info = tmp_path / "plug.cdmp"
    info.write_text(
        "[Core]\nName = P\nModule = __init__\n"
        "[Codimension]\nCategory = WizardInterface\nMinIDEVersion = 5.0.0\n"
        "MinPluginAPI = 1\nRequiredCapabilities =\nEntrypoint = __init__\n",
        encoding="utf-8",
    )
    (tmp_path / "__init__.py").write_text("X = 1\n", encoding="utf-8")
    sibling = tmp_path / "helper.py"
    sibling.write_text("Y = 1\n", encoding="utf-8")
    expected = capture_plugin_file_identity(info_path=str(info), module_filepath=str(tmp_path / "__init__"))
    assert expected.package_sha256
    sibling.write_text("Y = 2\n", encoding="utf-8")
    decision = validate_candidate_before_import(
        info_path=str(info),
        module_filepath=str(tmp_path / "__init__"),
        name="P",
        version="1",
        plugin_path=str(tmp_path),
        expected_identity=expected,
        ide_version="99.0.0",
        require_manifest=False,
    )
    assert decision.ok is False
    assert "changed" in decision.reason


def test_r251_lsp_root_uri_uses_canonical_helper(tmp_path: Path) -> None:
    spaced = tmp_path / "my project"
    spaced.mkdir()
    uri = _path_to_uri(str(spaced))
    assert uri == path_to_file_uri(os.path.abspath(str(spaced)))
    assert " " not in uri
    assert "%20" in uri or uri.startswith("file://")
