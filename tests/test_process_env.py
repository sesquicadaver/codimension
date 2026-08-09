# -*- coding: utf-8 -*-
"""T030 — ToolProcessEnvironment builder."""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "codimension"))


def test_build_tool_process_environment_inherits_and_overrides():
    from cdmplugins.process_env import build_tool_process_environment

    class FakeEnv:
        def __init__(self):
            self.values = {"PATH": "/usr/bin", "HOME": "/home/u", "VIRTUAL_ENV": "/venv"}

        def insert(self, key, value):
            self.values[key] = value

        def value(self, key, default=""):
            return self.values.get(key, default)

    env = build_tool_process_environment(
        "utf-8",
        overrides={"FOO": "bar"},
        env_factory=FakeEnv,
    )
    assert env.value("PATH") == "/usr/bin"
    assert env.value("HOME") == "/home/u"
    assert env.value("VIRTUAL_ENV") == "/venv"
    assert env.value("PYTHONIOENCODING") == "utf-8"
    assert env.value("FOO") == "bar"


def test_module_from_python_args():
    from cdmplugins.process_env import module_from_python_args

    assert module_from_python_args(["-m", "mypy", "x.py"]) == "mypy"
    assert module_from_python_args(["-m", "ruff", "check"]) == "ruff"
    assert module_from_python_args(["check"]) is None
    assert module_from_python_args(None) is None


def test_python_module_available_stdlib():
    from cdmplugins.process_env import python_module_available

    assert python_module_available(sys.executable, "json") is True
    assert python_module_available(sys.executable, "definitely_missing_mod_xyz") is False


def test_resolve_tool_falls_back_to_ide_when_module_missing(tmp_path, monkeypatch):
    """R178: project Python without tool → IDE Python that has it."""
    from unittest.mock import MagicMock

    from utils.analysis_environment import AnalysisEnvironment

    from cdmplugins import process_env as pe

    project_py = str(tmp_path / "proj" / "bin" / "python")
    ide_py = str(tmp_path / "ide" / "bin" / "python")
    site = str(tmp_path / "proj" / "lib" / "site-packages")

    def fake_available(python_path, module, **_kwargs):
        if module != "mypy":
            return False
        return python_path == ide_py

    monkeypatch.setattr(pe, "python_module_available", fake_available)
    monkeypatch.setattr(pe.sys, "executable", ide_py)

    analysis = AnalysisEnvironment(
        python_path=project_py,
        source_kind="configured",
        site_packages_roots=(site,),
        project_id="uuid",
    )
    monkeypatch.setattr(
        "utils.venvbootstrap.buildAnalysisEnvironment",
        lambda _project, for_tools=False: analysis,
    )

    class FakeEnv:
        def __init__(self):
            self.values = {}

        def insert(self, key, value):
            self.values[key] = value

        def value(self, key, default=""):
            return self.values.get(key, default)

    proj = MagicMock()
    python_path, env = pe.resolve_tool_python_and_environment(
        proj,
        module="mypy",
        env_factory=FakeEnv,
    )
    assert python_path == ide_py
    assert site in env.value("PYTHONPATH", "")


def test_build_tool_environ_applies_analysis_env(tmp_path):
    """R112 headless environ mirrors process_env analysis_env handling."""
    sys.modules.pop("utils.analysis_environment", None)

    from utils.analysis_environment import AnalysisEnvironment

    from codimension.infrastructure.process import build_tool_environ

    venv = tmp_path / ".venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")
    site = venv / "lib" / "python3.12" / "site-packages"
    site.mkdir(parents=True)
    analysis = AnalysisEnvironment.from_source(
        "auto",
        str(venv / "bin" / "python"),
        site_packages_roots=[str(site)],
        resolve_site_packages=False,
    )
    env = build_tool_environ(
        "utf-8",
        analysis_env=analysis,
        base={"PATH": "/bin", "PYTHONPATH": "/old"},
    )
    assert env["VIRTUAL_ENV"] == str(venv)
    assert env["PYTHONPATH"].startswith(str(site))
    assert "/old" in env["PYTHONPATH"]
    assert env["PYTHONIOENCODING"] == "utf-8"
