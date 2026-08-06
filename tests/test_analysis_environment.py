# -*- coding: utf-8 -*-
"""R110/R111: AnalysisEnvironment + buildAnalysisEnvironment constructor."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import parsers  # noqa: E402,F401
import pytest
from utils import venvbootstrap as vb
from utils.analysis_environment import (
    VALID_SOURCE_KINDS,
    AnalysisEnvironment,
)
from utils.run import getProjectPythonPath


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Temporary project root."""
    # Drop lint-driver stubs that may have replaced real utils modules.
    for name in (
        "utils.venvbootstrap",
        "utils.analysis_environment",
        "utils.run",
        "utils.misc",
        "utils",
    ):
        sys.modules.pop(name, None)
    root = tmp_path / "proj"
    root.mkdir()
    return root


def _fake_project(project_dir: Path, interpreter: str = "", uuid: str = "uuid-r110"):
    proj = MagicMock()
    proj.isLoaded.return_value = True
    proj.getProjectDir.return_value = str(project_dir) + os.sep
    proj.props = {"pythoninterpreter": interpreter, "uuid": uuid}
    return proj


def _make_venv_python(root: Path, name: str = "venv") -> str:
    """Create a minimal executable + site-packages under ``root/name``."""
    py = root / name / "bin" / "python"
    py.parent.mkdir(parents=True)
    py.write_text("#!/bin/sh\n", encoding="utf-8")
    os.chmod(py, 0o755)
    (root / name / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")
    (root / name / "lib" / "python3.12" / "site-packages").mkdir(parents=True)
    return str(py)


def test_analysis_environment_is_frozen() -> None:
    """Dataclass instances are immutable."""
    env = AnalysisEnvironment.from_source("ide", sys.executable, resolve_site_packages=False)
    with pytest.raises(Exception):
        env.python_path = "/tmp/other"  # type: ignore[misc]


def test_analysis_environment_rejects_unknown_kind() -> None:
    """Unknown source kinds raise ValueError."""
    with pytest.raises(ValueError, match="unknown source_kind"):
        AnalysisEnvironment.from_source("nope", sys.executable)


def test_analysis_environment_kinds_match_venvbootstrap_constants() -> None:
    """Source kinds stay aligned with venvbootstrap SOURCE_* values."""
    assert VALID_SOURCE_KINDS == {
        vb.SOURCE_CONFIGURED,
        vb.SOURCE_SESSION,
        vb.SOURCE_AUTO,
        vb.SOURCE_IDE,
        vb.SOURCE_INVALID,
    }


def test_build_analysis_environment_precedence(project_dir: Path) -> None:
    """R111: buildAnalysisEnvironment follows configured→session→auto→ide."""
    vb.clearSessionPythonInterpreter()

    prop_py = _make_venv_python(project_dir, "custom")
    env = vb.buildAnalysisEnvironment(_fake_project(project_dir, prop_py))
    assert env.source_kind == vb.SOURCE_CONFIGURED
    assert env.python_path == os.path.abspath(prop_py)
    assert env.project_id == "uuid-r110"
    assert len(env.site_packages_roots) == 1
    assert vb.getEffectiveProjectPython(_fake_project(project_dir, prop_py)) == env.python_path
    assert getProjectPythonPath(_fake_project(project_dir, prop_py)) == env.python_path

    sess = _make_venv_python(project_dir, "sess")
    vb.setSessionPythonInterpreter(sess)
    env = vb.buildAnalysisEnvironment(_fake_project(project_dir, ""))
    assert env.source_kind == vb.SOURCE_SESSION
    assert env.python_path == os.path.abspath(sess)
    vb.clearSessionPythonInterpreter()

    auto_py = _make_venv_python(project_dir, ".venv")
    env = vb.buildAnalysisEnvironment(_fake_project(project_dir, ""))
    assert env.source_kind == vb.SOURCE_AUTO
    assert env.python_path == os.path.abspath(auto_py)

    empty = project_dir / "emptyproj"
    empty.mkdir()
    env = vb.buildAnalysisEnvironment(_fake_project(empty, ""))
    assert env.source_kind == vb.SOURCE_IDE
    assert env.python_path == sys.executable
    assert env.site_packages_roots == ()
    assert vb.getEffectiveProjectPython(_fake_project(empty, "")) == sys.executable

    missing = str(project_dir / "gone" / "bin" / "python")
    broken = _fake_project(project_dir, missing)
    env = vb.buildAnalysisEnvironment(broken)
    assert env.source_kind == vb.SOURCE_INVALID
    assert "gone" in env.python_path
    assert env.site_packages_roots == ()
    # Effective path falls back; described path stays broken
    effective = vb.getEffectiveProjectPython(broken)
    assert effective == os.path.abspath(auto_py)
    assert effective != env.python_path


def test_build_analysis_environment_unloaded_project() -> None:
    """No loaded project → IDE environment without project id."""
    proj = MagicMock()
    proj.isLoaded.return_value = False
    env = vb.buildAnalysisEnvironment(proj)
    assert env.source_kind == vb.SOURCE_IDE
    assert env.python_path == sys.executable
    assert env.project_id is None


def test_analysis_environment_explicit_site_packages() -> None:
    """Caller-supplied site-packages roots are kept (deduped)."""
    env = AnalysisEnvironment.from_source(
        "configured",
        "/venv/bin/python",
        site_packages_roots=["/a", "/a", "", "/b"],
        resolve_site_packages=False,
        project_id="p1",
    )
    assert env.site_packages_roots == ("/a", "/b")
    assert env.project_id == "p1"
