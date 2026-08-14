# -*- coding: utf-8 -*-
"""Tests for D08 constraints gate helpers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_check_constraints_passes_on_repo():
    mod = _load("check_constraints", "scripts/check_constraints.py")
    assert mod.main.__code__  # importable
    # Run against repository root
    old = sys.argv
    try:
        sys.argv = ["check_constraints.py", "--root", str(ROOT)]
        assert mod.main() == 0
    finally:
        sys.argv = old


def test_parse_constraints_rejects_range(tmp_path):
    mod = _load("check_constraints_parse", "scripts/check_constraints.py")
    path = tmp_path / "constraints.txt"
    path.write_text("PyQt5>=5.15\n", encoding="utf-8")
    try:
        mod.parse_constraints(path)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_setup_uses_runtime_requirements():
    text = (ROOT / "setup.py").read_text(encoding="utf-8")
    assert "requirements-runtime.txt" in text
    assert "Could not find requirements-runtime.txt" in text
    runtime = (ROOT / "requirements-runtime.txt").read_text(encoding="utf-8")
    assert "PyQt5" in runtime
    assert "paramiko" in runtime
    assert "keyring" in runtime
    assert "pytest" not in runtime


def test_release_workflow_verifies_before_publish():
    text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "twine check" in text
    assert "offscreen_gui_smoke.py" in text
    assert "gh-action-pypi-publish" in text
    assert "secrets.PYPI_API_TOKEN" not in text
    assert "TWINE_PASSWORD" not in text
    assert "needs: verify" in text


def test_ci_gate_job_present():
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "ci-gate:" in text
    assert "-c constraints.txt" in text
