# -*- coding: utf-8 -*-
"""R110: AnalysisEnvironment dataclass parity with describeAnalysisPythonSource."""

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


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Temporary project root."""
    root = tmp_path / "proj"
    root.mkdir()
    return root


def _fake_project(project_dir: Path, interpreter: str = "", uuid: str = "uuid-r110"):
    proj = MagicMock()
    proj.isLoaded.return_value = True
    proj.getProjectDir.return_value = str(project_dir) + os.sep
    proj.props = {"pythoninterpreter": interpreter, "uuid": uuid}
    return proj


def _env_from_project(project) -> AnalysisEnvironment:
    """Mirror R111 intent: describe → AnalysisEnvironment (explicit in tests)."""
    kind, path = vb.describeAnalysisPythonSource(project)
    project_id = None
    if project is not None and project.isLoaded():
        project_id = (project.props.get("uuid") or "").strip() or None
    return AnalysisEnvironment.from_source(kind, path, project_id=project_id)


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


def test_analysis_environment_parity_with_describe(project_dir: Path) -> None:
    """from_source + describe cover configured/session/auto/ide/invalid."""
    vb.clearSessionPythonInterpreter()

    prop_py = str(project_dir / "custom" / "bin" / "python")
    Path(prop_py).parent.mkdir(parents=True)
    Path(prop_py).write_text("#!/bin/sh\n", encoding="utf-8")
    os.chmod(prop_py, 0o755)
    # Create a site-packages tree so roots resolve
    site = project_dir / "custom" / "lib" / "python3.12" / "site-packages"
    site.mkdir(parents=True)

    env = _env_from_project(_fake_project(project_dir, prop_py))
    assert env.source_kind == vb.SOURCE_CONFIGURED
    assert env.python_path == os.path.abspath(prop_py)
    assert env.project_id == "uuid-r110"
    assert env.site_packages_roots == (str(site),)
    assert env.is_broken is False

    sess = str(project_dir / "sess" / "bin" / "python")
    Path(sess).parent.mkdir(parents=True)
    Path(sess).write_text("#!/bin/sh\n", encoding="utf-8")
    os.chmod(sess, 0o755)
    (project_dir / "sess" / "lib" / "python3.12" / "site-packages").mkdir(parents=True)
    vb.setSessionPythonInterpreter(sess)
    env = _env_from_project(_fake_project(project_dir, ""))
    assert env.source_kind == vb.SOURCE_SESSION
    assert env.python_path == os.path.abspath(sess)
    assert len(env.site_packages_roots) == 1
    vb.clearSessionPythonInterpreter()

    auto_py = project_dir / ".venv" / "bin" / "python"
    auto_py.parent.mkdir(parents=True)
    (project_dir / ".venv" / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")
    auto_py.write_text("#!/bin/sh\n", encoding="utf-8")
    os.chmod(auto_py, 0o755)
    (project_dir / ".venv" / "lib" / "python3.12" / "site-packages").mkdir(parents=True)
    env = _env_from_project(_fake_project(project_dir, ""))
    assert env.source_kind == vb.SOURCE_AUTO
    assert env.python_path == os.path.abspath(str(auto_py))

    empty = project_dir / "emptyproj"
    empty.mkdir()
    env = _env_from_project(_fake_project(empty, ""))
    assert env.source_kind == vb.SOURCE_IDE
    assert env.python_path == sys.executable
    assert env.is_ide is True
    assert env.site_packages_roots == ()

    missing = str(project_dir / "gone" / "bin" / "python")
    env = _env_from_project(_fake_project(project_dir, missing))
    assert env.source_kind == vb.SOURCE_INVALID
    assert "gone" in env.python_path
    assert env.is_broken is True
    assert env.site_packages_roots == ()


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
