# -*- coding: utf-8 -*-
"""T030 — ToolProcessEnvironment builder."""

from __future__ import annotations

import os
import sys
import types

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
