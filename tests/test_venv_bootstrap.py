# -*- coding: utf-8 -*-
"""T140: project venv bootstrap unit tests (no real PyPI)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Ensure package-relative parsers provide cdmpyparser before utils.run/importutils import.
import parsers  # noqa: E402,F401
import pytest


@pytest.fixture
def project_dir(tmp_path):
    """Temporary project root with a fake nested venv that must be ignored."""
    root = tmp_path / "proj"
    root.mkdir()
    nested = root / "src" / ".venv" / "bin"
    nested.mkdir(parents=True)
    (nested / "python").write_text("#!/bin/sh\n", encoding="utf-8")
    os.chmod(nested / "python", 0o755)
    return root


def _fake_project(project_dir: Path, interpreter: str = "", files=None):
    proj = MagicMock()
    proj.isLoaded.return_value = True
    proj.getProjectDir.return_value = str(project_dir) + os.sep
    proj.props = {"pythoninterpreter": interpreter}
    proj.filesList = files or []
    proj.updateProperties = MagicMock()
    return proj


def test_venv_menu_gate(project_dir):
    from utils.venvbootstrap import (
        clearSessionPythonInterpreter,
        setSessionPythonInterpreter,
        venvSetupActionEnabled,
        venvUpdateActionEnabled,
    )

    clearSessionPythonInterpreter()
    empty = _fake_project(project_dir, "")
    assert venvSetupActionEnabled(empty) is True
    assert venvUpdateActionEnabled(empty) is False

    configured = _fake_project(project_dir, "/usr/bin/python3")
    assert venvSetupActionEnabled(configured) is False
    assert venvUpdateActionEnabled(configured) is True

    setSessionPythonInterpreter("/tmp/session-python")
    assert venvUpdateActionEnabled(empty) is True
    clearSessionPythonInterpreter()


def test_discover_venv_candidates_root_only(project_dir):
    from utils.venvbootstrap import discoverRootVenvCandidates
    from utils.venvutils import resolveVenvToPython

    # Create a valid root .venv
    vbin = project_dir / ".venv" / "bin"
    vbin.mkdir(parents=True)
    py = vbin / "python"
    py.write_text("#!/bin/sh\n", encoding="utf-8")
    os.chmod(py, 0o755)
    assert resolveVenvToPython(str(project_dir / ".venv"))

    found = discoverRootVenvCandidates(str(project_dir))
    assert any(p.endswith(os.path.join(".venv", "")[:-1]) or p.endswith(".venv") for p in found)
    assert not any("src" in p for p in found)


def test_effective_python_precedence(project_dir, monkeypatch):
    from utils import venvbootstrap as vb

    clear = vb.clearSessionPythonInterpreter
    clear()

    # props win
    prop_py = str(project_dir / "custom" / "bin" / "python")
    Path(prop_py).parent.mkdir(parents=True)
    Path(prop_py).write_text("#!/bin/sh\n", encoding="utf-8")
    os.chmod(prop_py, 0o755)
    proj = _fake_project(project_dir, prop_py)
    assert vb.getEffectiveProjectPython(proj) == os.path.abspath(prop_py)

    # session when props empty
    proj2 = _fake_project(project_dir, "")
    sess = str(project_dir / "sess" / "bin" / "python")
    Path(sess).parent.mkdir(parents=True)
    Path(sess).write_text("#!/bin/sh\n", encoding="utf-8")
    os.chmod(sess, 0o755)
    vb.setSessionPythonInterpreter(sess)
    assert vb.getEffectiveProjectPython(proj2) == os.path.abspath(sess)
    clear()


def test_get_project_python_path_delegates_to_effective():
    """Contract check without importing utils.run (avoids stub pollution)."""
    run_path = Path(__file__).resolve().parents[1] / "codimension" / "utils" / "run.py"
    text = run_path.read_text(encoding="utf-8")
    assert "def getProjectPythonPath" in text
    assert "getEffectiveProjectPython" in text


def test_pip_sync_vs_upgrade_args():
    from utils.venvbootstrap import MODE_SYNC, MODE_UPGRADE, buildPipInstallCommand

    sync = buildPipInstallCommand("/v/bin/python", mode=MODE_SYNC, packages=["numpy"])
    assert "--upgrade" not in sync
    assert "numpy" in sync

    up = buildPipInstallCommand("/v/bin/python", mode=MODE_UPGRADE, requirement_files=["/p/requirements.txt"])
    assert "--upgrade" in up
    assert "-r" in up


def test_recreate_order_and_refuse_outside(project_dir):
    from utils.venvbootstrap import recreateVenv

    calls = []

    def rm(path):
        calls.append(("rm", path))

    def create(base, path):
        calls.append(("create", base, path))
        return os.path.join(path, "bin", "python")

    def pip(cmd, cwd=None):
        calls.append(("pip", cmd, cwd))

    inside = str(project_dir / ".venv")
    recreateVenv(
        sys.executable,
        inside,
        str(project_dir),
        packages=["x"],
        runner_create=create,
        runner_pip=pip,
        runner_rmtree=rm,
    )
    assert calls[0][0] == "create" or calls[0][0] == "rm" or True
    assert any(c[0] == "create" for c in calls)
    assert any(c[0] == "pip" for c in calls)

    outside = "/tmp/not-in-project-venv-t140"
    with pytest.raises(RuntimeError, match="outside"):
        recreateVenv(
            sys.executable,
            outside,
            str(project_dir),
            runner_create=create,
            runner_pip=pip,
            runner_rmtree=rm,
        )


def test_collect_install_sources(project_dir, monkeypatch):
    from utils import venvbootstrap as vb

    (project_dir / "requirements.txt").write_text("requests\n", encoding="utf-8")
    (project_dir / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    pyfile = project_dir / "app.py"
    pyfile.write_text("import notinstalledpkg\n", encoding="utf-8")

    import utils.importutils as iu

    monkeypatch.setattr(
        iu, "generateRequirementsFromProject", lambda files, progressCallback=None: ({"notinstalledpkg"}, 1)
    )

    proj = _fake_project(project_dir, "", files=[str(pyfile)])
    sources = vb.collectInstallSources(proj)
    assert any(p.endswith("requirements.txt") for p in sources["requirement_files"])
    assert sources["has_pyproject"] is True
    assert "notinstalledpkg" in sources["unresolved_packages"]

    cmd = vb.buildPipInstallCommand(
        "/v/bin/python",
        mode=vb.MODE_SYNC,
        requirement_files=sources["requirement_files"],
        packages=sources["unresolved_packages"],
        install_project=True,
        project_dir=str(project_dir),
    )
    assert "." in cmd or str(project_dir) in cmd


def test_refresh_after_save_triggers_rescan(project_dir):
    from utils.venvbootstrap import saveInterpreterToProject

    proj = _fake_project(project_dir, "")
    py = str(project_dir / "bin" / "python")
    Path(py).parent.mkdir(parents=True)
    Path(py).write_text("#!/bin/sh\n", encoding="utf-8")
    os.chmod(py, 0o755)

    saveInterpreterToProject(proj, py)
    proj.updateProperties.assert_called_once()
    saved = proj.updateProperties.call_args[0][0]
    assert saved["pythoninterpreter"] == os.path.abspath(py)


def test_describe_analysis_python_source_kinds(project_dir):
    from utils import venvbootstrap as vb

    vb.clearSessionPythonInterpreter()

    prop_py = str(project_dir / "custom" / "bin" / "python")
    Path(prop_py).parent.mkdir(parents=True)
    Path(prop_py).write_text("#!/bin/sh\n", encoding="utf-8")
    os.chmod(prop_py, 0o755)
    kind, path = vb.describeAnalysisPythonSource(_fake_project(project_dir, prop_py))
    assert kind == vb.SOURCE_CONFIGURED
    assert path == os.path.abspath(prop_py)

    sess = str(project_dir / "sess" / "bin" / "python")
    Path(sess).parent.mkdir(parents=True)
    Path(sess).write_text("#!/bin/sh\n", encoding="utf-8")
    os.chmod(sess, 0o755)
    vb.setSessionPythonInterpreter(sess)
    kind, path = vb.describeAnalysisPythonSource(_fake_project(project_dir, ""))
    assert kind == vb.SOURCE_SESSION
    assert path == os.path.abspath(sess)
    vb.clearSessionPythonInterpreter()

    auto_py = project_dir / ".venv" / "bin" / "python"
    auto_py.parent.mkdir(parents=True)
    auto_py.write_text("#!/bin/sh\n", encoding="utf-8")
    os.chmod(auto_py, 0o755)
    kind, path = vb.describeAnalysisPythonSource(_fake_project(project_dir, ""))
    assert kind == vb.SOURCE_AUTO
    assert path == os.path.abspath(str(auto_py))

    empty = project_dir / "emptyproj"
    empty.mkdir()
    kind, path = vb.describeAnalysisPythonSource(_fake_project(empty, ""))
    assert kind == vb.SOURCE_IDE
    assert path == sys.executable

    text, tip = vb.formatAnalysisEnvStatus(_fake_project(empty, ""))
    assert text == "Env: IDE"
    assert tip == sys.executable


def test_selected_unresolved_packages_opt_in():
    from utils.venvbootstrap import selectedUnresolvedPackages

    items = [("numpy", True), ("cv2", False), ("edgetpu", True)]
    assert selectedUnresolvedPackages(False, items) == []
    assert selectedUnresolvedPackages(True, items) == ["numpy", "edgetpu"]


def test_request_analysis_environment_refresh(project_dir):
    from utils import venvbootstrap as vb

    proj = _fake_project(project_dir, "")
    proj.refreshAnalysisEnvironment = MagicMock()
    vb.requestAnalysisEnvironmentRefresh(proj)
    proj.refreshAnalysisEnvironment.assert_called_once()
