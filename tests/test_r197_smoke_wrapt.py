# -*- coding: utf-8 -*-
"""R197: wrapt/inspect compat and smoke graceful shutdown."""

from __future__ import annotations

import importlib
import inspect
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ensure_wrapt_compat_restores_formatargspec(monkeypatch) -> None:
    """Shim installs formatargspec when missing."""
    from codimension.inspect_compat import ensure_wrapt_compat, formatargspec

    monkeypatch.delattr(inspect, "formatargspec", raising=False)
    assert ensure_wrapt_compat() is True
    assert inspect.formatargspec is formatargspec
    assert ensure_wrapt_compat() is False


def test_wrapt_imports_after_compat() -> None:
    """wrapt 1.12 must import after the shim (no pip --no-deps upgrade)."""
    from codimension.inspect_compat import ensure_wrapt_compat

    ensure_wrapt_compat()
    for name in list(sys.modules):
        if name == "wrapt" or name.startswith("wrapt."):
            del sys.modules[name]
    wrapt = importlib.import_module("wrapt")
    assert wrapt.__version__.startswith("1.12")


def test_r276_pylint_python_argv_bootstraps_shim() -> None:
    """R276: argv uses ``-c`` bootstrap, not ``-m pylint`` (wrapt loads too early)."""
    from codimension.inspect_compat import pylint_python_argv

    argv = pylint_python_argv(["--version"])
    assert argv[0] == "-c"
    assert "ensure_wrapt_compat" in argv[1]
    assert "run_pylint" in argv[1]
    assert argv[2:] == ["--version"]
    assert "-m" not in argv


def test_r276_pylint_subprocess_version_ok() -> None:
    """Bare ``python -m pylint`` fails on 3.12; wrapt-safe argv must succeed."""
    from codimension.inspect_compat import pylint_python_argv

    bare = subprocess.run(
        [sys.executable, "-m", "pylint", "--version"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if sys.version_info >= (3, 11):
        assert bare.returncode != 0
        assert "formatargspec" in (bare.stderr + bare.stdout)

    safe = subprocess.run(
        [sys.executable, *pylint_python_argv(["--version"])],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert safe.returncode == 0, f"rc={safe.returncode}\nstdout:\n{safe.stdout}\nstderr:\n{safe.stderr}"
    assert "pylint" in safe.stdout.lower()


def test_smoke_script_prefers_normal_exit() -> None:
    """R274: default smoke path must not hard-exit; cleanup still runs first."""
    text = (ROOT / "scripts" / "offscreen_gui_smoke.py").read_text(encoding="utf-8")
    assert "_shutdown_smoke" in text
    finally_idx = text.index("finally:")
    assert "_shutdown_smoke(app, main_window)" in text[finally_idx:]
    # Hard exit is opt-in via CDM_SMOKE_HARD_EXIT, not the default success path.
    assert "CDM_SMOKE_HARD_EXIT" in text[finally_idx:]
    assert text.index("_shutdown_smoke(app, main_window)", finally_idx) < text.index("CDM_SMOKE_HARD_EXIT", finally_idx)


def test_ctl_has_no_wrapt_nodeps_hack() -> None:
    """Install path must not run manual wrapt --no-deps."""
    text = (ROOT / "scripts" / "codimension_ctl.sh").read_text(encoding="utf-8")
    assert "wrapt>=1.14" not in text
    assert "inspect_compat" in text


def test_offscreen_smoke_subprocess_ok() -> None:
    """Graceful-shutdown smoke still exits 0 with plugins loaded."""
    env = dict(**{k: v for k, v in __import__("os").environ.items()})
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    # CI hosts still hit PyQt atexit segfaults (rc=-11) without the escape hatch.
    env["CDM_SMOKE_HARD_EXIT"] = "1"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "offscreen_gui_smoke.py")],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert result.returncode == 0, f"rc={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "plugins_active=" in result.stdout
