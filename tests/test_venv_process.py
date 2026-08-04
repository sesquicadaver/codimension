# -*- coding: utf-8 -*-
"""A03: non-blocking VENV process runner (offscreen Qt)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_CODIM_UI = Path(__file__).resolve().parents[1] / "codimension" / "ui"


def _purge_stub_ui_modules() -> None:
    """Drop stub ``ui`` / ``ui.qt`` left in ``sys.modules`` by other tests."""
    for name in list(sys.modules):
        if name != "ui" and not name.startswith("ui."):
            continue
        mod = sys.modules.get(name)
        path = getattr(mod, "__file__", None) or ""
        # Stubs are ModuleType with no file, or non-package paths.
        if not path or "codimension/ui" not in path.replace("\\", "/"):
            del sys.modules[name]


@pytest.fixture
def qapp_ready(qapp):
    """Ensure real ``ui.qt`` is importable after suite-wide stubs."""
    _purge_stub_ui_modules()
    if str(_CODIM_UI.parent) not in sys.path:
        sys.path.insert(0, str(_CODIM_UI.parent))
    importlib.invalidate_caches()
    import ui.qt as qt  # noqa: F401

    assert hasattr(qt, "QEventLoop"), "ui.qt stub still active"
    assert hasattr(qt, "QProgressDialog"), "QProgressDialog not exported"
    # Force reload of venvprocess against the real qt module.
    sys.modules.pop("ui.venvprocess", None)
    return qapp


def test_run_argv_with_progress_success(qapp_ready):
    from ui.venvprocess import run_argv_with_progress

    out, err = run_argv_with_progress(
        None,
        [sys.executable, "-c", "print('venv-a03-ok')"],
        title="test",
        label="echo",
    )
    assert "venv-a03-ok" in out
    assert err == "" or err is not None


def test_run_argv_with_progress_nonzero_raises(qapp_ready):
    from ui.venvprocess import run_argv_with_progress

    with pytest.raises(RuntimeError, match="command failed"):
        run_argv_with_progress(
            None,
            [sys.executable, "-c", "raise SystemExit(7)"],
            title="test",
        )


def test_run_pip_with_progress_refuses_ide(qapp_ready):
    from ui.venvprocess import run_pip_with_progress

    with pytest.raises(RuntimeError, match="IDE"):
        run_pip_with_progress(None, [sys.executable, "-m", "pip", "install", "x"])


def test_venv_dialogs_use_async_runner():
    """Dialogs must call QProcess helpers, not sync subprocess wrappers."""
    text = Path(__file__).resolve().parents[1] / "codimension" / "ui" / "venvsetupdlg.py"
    src = text.read_text(encoding="utf-8")
    assert "create_venv_with_progress" in src
    assert "run_pip_with_progress" in src
    assert "runPipInstall(" not in src
    assert "createVenv(base" not in src and "createVenv(self" not in src
