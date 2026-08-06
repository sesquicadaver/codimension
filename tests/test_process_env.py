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
