# -*- coding: utf-8 -*-
"""R120: DependencyManifest formalizes collectInstallSources."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import parsers  # noqa: E402,F401
import pytest
from utils import venvbootstrap as vb
from utils.dependency_manifest import (
    DependencyManifest,
    buildDependencyManifest,
    buildDependencyManifestFromDir,
)


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    return root


def _fake_project(project_dir: Path, files=None, uuid: str = "uuid-r120"):
    proj = MagicMock()
    proj.isLoaded.return_value = True
    proj.getProjectDir.return_value = str(project_dir) + os.sep
    proj.props = {"uuid": uuid, "pythoninterpreter": ""}
    proj.filesList = files or []
    return proj


def test_manifest_lock_hint_prefers_requirements_txt(project_dir: Path) -> None:
    req = project_dir / "requirements.txt"
    req.write_text("requests\n", encoding="utf-8")
    (project_dir / "requirements-dev.txt").write_text("pytest\n", encoding="utf-8")
    man = buildDependencyManifest(
        _fake_project(project_dir),
        unresolved_packages=["alpha"],
    )
    assert man.has_pyproject is False
    assert len(man.requirement_files) == 2
    assert man.lock_hint() == f"pip install -r {req.resolve()}"
    assert man.as_dict()["unresolved_packages"] == ["alpha"]


def test_manifest_lock_hint_pyproject_and_packages(project_dir: Path) -> None:
    (project_dir / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    man = buildDependencyManifest(
        _fake_project(project_dir),
        unresolved_packages=["beta", "alpha"],
    )
    assert man.has_pyproject is True
    assert man.unresolved_packages == ("alpha", "beta")
    assert man.lock_hint().startswith("pip install -e ")
    assert os.path.abspath(str(project_dir)) in man.lock_hint()


def test_manifest_lock_hint_packages_only(project_dir: Path) -> None:
    man = DependencyManifest(unresolved_packages=("numpy", "requests"))
    assert man.lock_hint() == "pip install numpy requests"


def test_manifest_write_requirements(project_dir: Path) -> None:
    man = DependencyManifest(unresolved_packages=("zzz", "aaa"))
    out = project_dir / "requirements.txt"
    n = man.write_requirements(str(out), mode="w")
    assert n == 2
    text = out.read_text(encoding="utf-8")
    assert text == "aaa\nzzz\n"


def test_collect_install_sources_uses_manifest(project_dir: Path, monkeypatch) -> None:
    (project_dir / "requirements.txt").write_text("x\n", encoding="utf-8")
    (project_dir / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    pyfile = project_dir / "app.py"
    pyfile.write_text("import notinstalledpkg\n", encoding="utf-8")

    import utils.importutils as iu

    monkeypatch.setattr(
        iu,
        "generateRequirementsFromProject",
        lambda files, progressCallback=None: ({"notinstalledpkg"}, 1),
    )
    sources = vb.collectInstallSources(_fake_project(project_dir, files=[str(pyfile)]))
    assert sources["has_pyproject"] is True
    assert "notinstalledpkg" in sources["unresolved_packages"]
    assert any(p.endswith("requirements.txt") for p in sources["requirement_files"])


def test_build_from_dir_with_explicit_packages(project_dir: Path) -> None:
    man = buildDependencyManifestFromDir(str(project_dir), unresolved_packages=["one", "two"])
    assert man.project_dir == os.path.abspath(str(project_dir))
    assert man.unresolved_packages == ("one", "two")
    assert man.project_id is None


def test_export_script_json(project_dir: Path, monkeypatch) -> None:
    """CLI prints JSON lock_hint without scanning imports when --packages given."""
    import scripts.export_dependency_manifest as cli

    (project_dir / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    rc = cli.main([str(project_dir), "--json", "--packages", "pkgx"])
    assert rc == 0
