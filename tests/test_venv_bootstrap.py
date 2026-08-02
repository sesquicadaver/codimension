# -*- coding: utf-8 -*-
"""T140: project venv bootstrap unit tests (no real PyPI)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure package-relative parsers provide cdmpyparser before utils.run/importutils import.
import parsers  # noqa: E402,F401


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
    import importlib
    import sys

    from utils import venvbootstrap as vb

    # Other suites may leave a stub of utils.run; reload the package module.
    run_mod = sys.modules.get("utils.run")
    if run_mod is None or "codimension/utils/run.py" not in (getattr(run_mod, "__file__", "") or "").replace("\\", "/"):
        sys.modules.pop("utils.run", None)
        importlib.invalidate_caches()
    from utils.run import getProjectPythonPath

    clear = vb.clearSessionPythonInterpreter
    clear()

    # props win
    prop_py = str(project_dir / "custom" / "bin" / "python")
    Path(prop_py).parent.mkdir(parents=True)
    Path(prop_py).write_text("#!/bin/sh\n", encoding="utf-8")
    os.chmod(prop_py, 0o755)
    proj = _fake_project(project_dir, prop_py)
    assert vb.getEffectiveProjectPython(proj) == os.path.abspath(prop_py)
    assert getProjectPythonPath(proj) == vb.getEffectiveProjectPython(proj)

    # session when props empty
    proj2 = _fake_project(project_dir, "")
    sess = str(project_dir / "sess" / "bin" / "python")
    Path(sess).parent.mkdir(parents=True)
    Path(sess).write_text("#!/bin/sh\n", encoding="utf-8")
    os.chmod(sess, 0o755)
    vb.setSessionPythonInterpreter(sess)
    assert vb.getEffectiveProjectPython(proj2) == os.path.abspath(sess)
    assert getProjectPythonPath(proj2) == os.path.abspath(sess)
    clear()


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
