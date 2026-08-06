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

    # Broken configured path: allow VENV… reattach (audit @ 9df7eca7)
    broken = _fake_project(project_dir, str(project_dir / "gone" / "bin" / "python"))
    assert venvSetupActionEnabled(broken) is True
    assert venvUpdateActionEnabled(broken) is True

    setSessionPythonInterpreter("/tmp/session-python")
    assert venvUpdateActionEnabled(empty) is True
    clearSessionPythonInterpreter()


def test_discover_venv_candidates_root_only(project_dir):
    from utils.venvbootstrap import discoverRootVenvCandidates
    from utils.venvutils import resolveVenvToPython

    # Create a valid root .venv
    vbin = project_dir / ".venv" / "bin"
    vbin.mkdir(parents=True)
    (project_dir / ".venv" / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")
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


def _fake_probe(path: str, *, version=None, is_venv=True, prefix=None):
    """Probe stub for recreate tests (avoids executing fake #!/bin/sh pythons)."""
    root = str(Path(path).resolve().parent.parent)
    return {
        "executable": path,
        "prefix": prefix or root,
        "base_prefix": "/usr",
        "version_info": list(version or sys.version_info[:3]),
        "is_venv": is_venv,
    }


def test_recreate_order_and_refuse_outside(project_dir):
    from utils.venvbootstrap import recreateVenv
    from utils.venvutils import resolveVenvToPython

    calls = []
    inside = str(project_dir / ".venv")
    Path(inside).mkdir()
    (Path(inside) / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")
    bin_dir = Path(inside) / "bin"
    bin_dir.mkdir()
    old_py = bin_dir / "python"
    old_py.write_text("#!/bin/sh\n", encoding="utf-8")
    os.chmod(old_py, 0o755)
    (Path(inside) / "old.txt").write_text("keep-until-commit", encoding="utf-8")

    def create(base, path):
        calls.append(("create", base, path))
        assert path != inside, "create must target staging, not live venv"
        assert (Path(inside) / "old.txt").is_file(), "old venv must survive until commit"
        Path(path).mkdir(parents=True)
        (Path(path) / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")
        bin_dir = Path(path) / "bin"
        bin_dir.mkdir()
        py = bin_dir / "python"
        py.write_text("#!/bin/sh\n", encoding="utf-8")
        os.chmod(py, 0o755)
        return str(py)

    def pip(cmd, cwd=None, project_dir=None):
        calls.append(("pip", cmd, cwd))
        assert (Path(inside) / "old.txt").is_file(), "old venv must survive pip failure window"

    recreateVenv(
        sys.executable,
        inside,
        str(project_dir),
        packages=["x"],
        runner_create=create,
        runner_pip=pip,
        runner_probe=_fake_probe,
    )
    kinds = [c[0] for c in calls]
    assert kinds == ["create", "pip"]
    assert not (Path(inside) / "old.txt").exists()
    assert resolveVenvToPython(inside)

    outside = "/tmp/not-in-project-venv-t140"
    with pytest.raises(RuntimeError, match="outside"):
        recreateVenv(
            sys.executable,
            outside,
            str(project_dir),
            runner_create=create,
            runner_pip=pip,
            runner_probe=_fake_probe,
        )


def test_recreate_rolls_back_on_create_failure(project_dir):
    """D02/B07: failed create must leave the previous venv intact."""
    from utils.venvbootstrap import recreateVenv

    inside = project_dir / ".venv"
    inside.mkdir()
    marker = inside / "marker.txt"
    marker.write_text("original", encoding="utf-8")
    (inside / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")
    bin_dir = inside / "bin"
    bin_dir.mkdir()
    py = bin_dir / "python"
    py.write_text("#!/bin/sh\n", encoding="utf-8")
    os.chmod(py, 0o755)

    def boom(_base, _path):
        raise RuntimeError("simulated create failure")

    with pytest.raises(RuntimeError, match="simulated create failure"):
        recreateVenv(
            sys.executable,
            str(inside),
            str(project_dir),
            runner_create=boom,
            runner_pip=lambda *_a, **_k: None,
            runner_probe=_fake_probe,
        )
    assert marker.read_text(encoding="utf-8") == "original"
    assert not any(project_dir.glob(".cdm-venv-stage-*"))


def test_recreate_rolls_back_on_pip_failure(project_dir):
    """D02/B07: failed pip must discard staging and keep the previous venv."""
    from utils.venvbootstrap import recreateVenv

    inside = project_dir / ".venv"
    inside.mkdir()
    marker = inside / "marker.txt"
    marker.write_text("original", encoding="utf-8")
    (inside / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")
    bin_dir = inside / "bin"
    bin_dir.mkdir()
    py = bin_dir / "python"
    py.write_text("#!/bin/sh\n", encoding="utf-8")
    os.chmod(py, 0o755)

    def create(_base, path):
        Path(path).mkdir(parents=True)
        (Path(path) / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")
        b = Path(path) / "bin"
        b.mkdir()
        p = b / "python"
        p.write_text("#!/bin/sh\n", encoding="utf-8")
        os.chmod(p, 0o755)
        return str(p)

    def pip_fail(_cmd, cwd=None):
        raise RuntimeError("simulated pip failure")

    with pytest.raises(RuntimeError, match="simulated pip failure"):
        recreateVenv(
            sys.executable,
            str(inside),
            str(project_dir),
            packages=["x"],
            runner_create=create,
            runner_pip=pip_fail,
            runner_probe=_fake_probe,
        )
    assert marker.read_text(encoding="utf-8") == "original"
    assert not any(project_dir.glob(".cdm-venv-stage-*"))


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
    (project_dir / ".venv" / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")
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


def test_stale_configured_interpreter_is_invalid(project_dir):
    from utils import venvbootstrap as vb

    vb.clearSessionPythonInterpreter()
    missing = str(project_dir / "gone" / "bin" / "python")
    proj = _fake_project(project_dir, missing)
    kind, path = vb.describeAnalysisPythonSource(proj)
    assert kind == vb.SOURCE_INVALID
    assert "gone" in path
    text, tip = vb.formatAnalysisEnvStatus(proj)
    assert text == "Env: broken"
    assert "configured missing" in tip
    # Analysis may fall back, but mutate must refuse
    effective = vb.getEffectiveProjectPython(proj)
    assert effective  # auto or IDE
    with pytest.raises(RuntimeError, match="missing|not executable|configured"):
        vb.requireMutableProjectPython(proj)


def test_refuse_mutate_ide_python(project_dir):
    from utils import venvbootstrap as vb

    vb.clearSessionPythonInterpreter()
    with pytest.raises(RuntimeError, match="IDE"):
        vb.assertSafeMutableProjectPython(sys.executable)
    with pytest.raises(RuntimeError, match="IDE|no project venv"):
        vb.requireMutableProjectPython(_fake_project(project_dir, ""))


def test_request_analysis_environment_refresh(project_dir):
    from utils import venvbootstrap as vb

    proj = _fake_project(project_dir, "")
    proj.refreshAnalysisEnvironment = MagicMock()
    vb.requestAnalysisEnvironmentRefresh(proj)
    proj.refreshAnalysisEnvironment.assert_called_once()


def test_validate_venv_destination_guards(project_dir, tmp_path):
    """C01 / audit P0 @ 9df7eca7: fail-closed create destination checks."""
    from utils import venvbootstrap as vb

    with pytest.raises(RuntimeError, match="empty"):
        vb.validateVenvDestination("", str(project_dir))

    with pytest.raises(RuntimeError, match="project root"):
        vb.validateVenvDestination(str(project_dir), str(project_dir))

    with pytest.raises(RuntimeError, match="outside"):
        vb.validateVenvDestination(str(tmp_path / "elsewhere" / ".venv"), str(project_dir))

    with pytest.raises(RuntimeError, match="IDE environment"):
        vb.validateVenvDestination(sys.prefix, project_dir=None)

    # Same refusal when IDE prefix happens to sit under the project root
    ide = os.path.realpath(sys.prefix)
    ide_parent = os.path.dirname(ide)
    if ide_parent and os.path.normpath(ide) != os.path.normpath(ide_parent):
        if vb.isPathInsideProject(ide, ide_parent):
            with pytest.raises(RuntimeError, match="IDE environment"):
                vb.validateVenvDestination(ide, ide_parent)

    existing = project_dir / ".venv"
    existing.mkdir()
    (existing / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")
    bin_dir = existing / "bin"
    bin_dir.mkdir()
    py = bin_dir / "python"
    py.write_text("#!/bin/sh\n", encoding="utf-8")
    os.chmod(py, 0o755)
    with pytest.raises(RuntimeError, match="already exists"):
        vb.validateVenvDestination(str(existing), str(project_dir), for_recreate=False)
    assert vb.validateVenvDestination(str(existing), str(project_dir), for_recreate=True) == os.path.abspath(
        str(existing)
    )

    nonempty = project_dir / "stuff"
    nonempty.mkdir()
    (nonempty / "file.txt").write_text("x", encoding="utf-8")
    with pytest.raises(RuntimeError, match="not empty"):
        vb.validateVenvDestination(str(nonempty), str(project_dir))

    link = project_dir / "link-venv"
    link.symlink_to(existing)
    with pytest.raises(RuntimeError, match="symlink"):
        vb.validateVenvDestination(str(link), str(project_dir))

    fresh = project_dir / ".venv-new"
    assert vb.validateVenvDestination(str(fresh), str(project_dir)) == os.path.abspath(str(fresh))


def test_create_venv_refuses_ide_prefix(project_dir, monkeypatch):
    from utils import venvbootstrap as vb

    def boom(*_a, **_k):
        raise AssertionError("subprocess must not run for unsafe destination")

    monkeypatch.setattr(vb.subprocess, "run", boom)
    with pytest.raises(RuntimeError, match="IDE environment"):
        vb.createVenv(sys.executable, sys.prefix, project_dir=None)


def test_probe_python_interpreter_self():
    """C02: live probe against the test interpreter returns required fields."""
    from utils.venvbootstrap import probePythonInterpreter

    info = probePythonInterpreter(sys.executable)
    assert info["executable"]
    assert "prefix" in info and "base_prefix" in info
    assert list(info["version_info"][:2]) == list(sys.version_info[:2])
    assert "is_venv" in info


def test_assert_mutable_requires_venv_probe(project_dir, tmp_path, monkeypatch):
    """C02: bare executable without venv must be refused for mutation."""
    from utils import venvbootstrap as vb

    bare = tmp_path / "bare-python"
    bare.write_text("#!/bin/sh\n", encoding="utf-8")
    os.chmod(bare, 0o755)

    def fake_probe(path):
        return {
            "executable": path,
            "prefix": str(tmp_path),
            "base_prefix": str(tmp_path),
            "version_info": list(sys.version_info[:3]),
            "is_venv": False,
        }

    monkeypatch.setattr(vb, "probePythonInterpreter", fake_probe)
    monkeypatch.setattr(vb, "isIdePythonEnvironment", lambda _p: False)
    with pytest.raises(RuntimeError, match="not a virtual environment"):
        vb.assertSafeMutableProjectPython(str(bare), project_dir=str(project_dir))


def test_resolve_recreate_base_prefers_cfg_executable(project_dir, monkeypatch):
    """C03: recreate base comes from pyvenv.cfg, not a silent IDE version swap."""
    from utils import venvbootstrap as vb

    root = project_dir / ".venv"
    bin_dir = root / "bin"
    bin_dir.mkdir(parents=True)
    py = bin_dir / "python"
    py.write_text("#!/bin/sh\n", encoding="utf-8")
    os.chmod(py, 0o755)
    base = project_dir / "base-python"
    base.write_text("#!/bin/sh\n", encoding="utf-8")
    os.chmod(base, 0o755)
    (root / "pyvenv.cfg").write_text(
        f"home = {project_dir}\nexecutable = {base}\nversion = {sys.version_info[0]}.{sys.version_info[1]}.0\n",
        encoding="utf-8",
    )

    def probe(path):
        path = os.path.abspath(path)
        if path == os.path.abspath(str(py)):
            return {
                "executable": path,
                "prefix": str(root),
                "base_prefix": "/usr",
                "version_info": list(sys.version_info[:3]),
                "is_venv": True,
            }
        if path == os.path.abspath(str(base)):
            return {
                "executable": path,
                "prefix": "/usr",
                "base_prefix": "/usr",
                "version_info": list(sys.version_info[:3]),
                "is_venv": False,
            }
        raise RuntimeError(f"unexpected probe: {path}")

    monkeypatch.setattr(vb, "probePythonInterpreter", probe)
    monkeypatch.setattr(vb, "isIdePythonEnvironment", lambda p: os.path.realpath(p) == os.path.realpath(sys.executable))
    assert vb.resolveRecreateBasePython(str(py)) == os.path.abspath(str(base))


def test_resolve_recreate_base_refuses_version_mismatch(project_dir, monkeypatch):
    """C03: IDE sys.executable must not win when major.minor differs."""
    from utils import venvbootstrap as vb

    root = project_dir / ".venv"
    bin_dir = root / "bin"
    bin_dir.mkdir(parents=True)
    py = bin_dir / "python"
    py.write_text("#!/bin/sh\n", encoding="utf-8")
    os.chmod(py, 0o755)
    (root / "pyvenv.cfg").write_text("home = /nonexistent\nversion = 3.10.0\n", encoding="utf-8")

    def probe(path):
        path = os.path.abspath(path)
        if path == os.path.abspath(str(py)):
            return {
                "executable": path,
                "prefix": str(root),
                "base_prefix": "/usr",
                "version_info": [3, 10, 0],
                "is_venv": True,
            }
        raise RuntimeError("no candidate")

    monkeypatch.setattr(vb, "probePythonInterpreter", probe)
    monkeypatch.setattr(vb.shutil, "which", lambda _name: None)
    monkeypatch.setattr(vb.sys, "version_info", (3, 13, 0, "final", 0))
    with pytest.raises(RuntimeError, match="cannot resolve base Python 3.10"):
        vb.resolveRecreateBasePython(str(py))


def _make_root_venv(project_dir: Path, name: str = ".venv") -> str:
    """Create a minimal root venv and return its python path."""
    root = project_dir / name
    bin_dir = root / "bin"
    bin_dir.mkdir(parents=True)
    (root / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")
    py = bin_dir / "python"
    py.write_text("#!/bin/sh\n", encoding="utf-8")
    os.chmod(py, 0o755)
    return str(py)


def test_maybe_auto_attach_disabled_is_noop(project_dir):
    """R114: default-off setting must not attach."""
    from utils import venvbootstrap as vb

    vb.clearSessionPythonInterpreter()
    _make_root_venv(project_dir)
    proj = _fake_project(project_dir, "")
    assert vb.maybeAutoAttachProjectVenv(proj, enabled=False) is None
    assert vb.getSessionPythonInterpreter() == ""


def test_maybe_auto_attach_sets_session(project_dir):
    """R114: enabled attach sets session overlay (does not rewrite props)."""
    from utils import venvbootstrap as vb

    vb.clearSessionPythonInterpreter()
    py = _make_root_venv(project_dir)
    proj = _fake_project(project_dir, "")
    attached = vb.maybeAutoAttachProjectVenv(proj, enabled=True)
    assert attached == os.path.abspath(py)
    assert vb.getSessionPythonInterpreter() == os.path.abspath(py)
    assert proj.props["pythoninterpreter"] == ""
    kind, path = vb.describeAnalysisPythonSource(proj)
    assert kind == vb.SOURCE_SESSION
    assert path == os.path.abspath(py)
    vb.clearSessionPythonInterpreter()


def test_maybe_auto_attach_skips_configured(project_dir):
    """R114: existing configured interpreter wins over auto-attach."""
    from utils import venvbootstrap as vb

    vb.clearSessionPythonInterpreter()
    _make_root_venv(project_dir)
    configured = _make_root_venv(project_dir, "custom")
    proj = _fake_project(project_dir, configured)
    assert vb.maybeAutoAttachProjectVenv(proj, enabled=True) is None
    assert vb.getSessionPythonInterpreter() == ""


def test_maybe_auto_attach_persist_to_project(project_dir):
    """R114: persist_to_project writes props and clears session overlay."""
    from utils import venvbootstrap as vb

    vb.clearSessionPythonInterpreter()
    py = _make_root_venv(project_dir)
    proj = _fake_project(project_dir, "")
    proj.saveProject = MagicMock()
    attached = vb.maybeAutoAttachProjectVenv(proj, enabled=True, persist_to_project=True)
    assert attached == os.path.abspath(py)
    assert proj.props["pythoninterpreter"]
    proj.saveProject.assert_called_once()
    assert vb.getSessionPythonInterpreter() == ""
    kind, _ = vb.describeAnalysisPythonSource(proj)
    assert kind == vb.SOURCE_CONFIGURED
