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
    assert "create_venv_in_place_with_progress" in src
    assert "run_pip_with_progress" in src
    assert "selectedBaseInterpreter" in src
    assert "runPipInstall(" not in src
    assert "createVenv(base" not in src and "createVenv(self" not in src


def test_selected_base_interpreter_ignores_stale_item_data(qapp_ready):
    """D01: Browse/setEditText must not leave currentData() as the create base."""
    from ui.qt import QComboBox
    from ui.venvsetupdlg import selectedBaseInterpreter

    combo = QComboBox()
    combo.setEditable(True)
    combo.addItem(f"System default ({sys.executable})", sys.executable)
    combo.setCurrentIndex(0)
    assert selectedBaseInterpreter(combo) == sys.executable

    alt = "/opt/custom/bin/python3.10"
    # Reproduce the historical bug path: edit text without clearing index.
    combo.setEditText(alt)
    assert combo.currentData() == sys.executable
    assert selectedBaseInterpreter(combo) == alt

    combo.setCurrentIndex(0)
    combo.setCurrentIndex(-1)
    combo.setEditText(alt)
    assert selectedBaseInterpreter(combo) == alt


def test_create_venv_with_progress_uses_base_in_argv(qapp_ready, tmp_path, monkeypatch):
    """D01: QProcess argv must start with the selected base interpreter."""
    from ui import venvprocess as vp

    captured: list[list[str]] = []

    def fake_run(parent, argv, **kwargs):
        captured.append(list(argv))
        dest = Path(argv[-1])
        bin_dir = dest / "bin"
        bin_dir.mkdir(parents=True)
        (dest / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")
        py = bin_dir / "python"
        py.write_text("#!/bin/sh\n", encoding="utf-8")
        py.chmod(0o755)
        return "", ""

    monkeypatch.setattr(vp, "run_argv_with_progress", fake_run)
    base = "/usr/bin/python3.10-not-ide"
    dest = tmp_path / "proj" / ".venv"
    dest.parent.mkdir()
    out = vp.create_venv_with_progress(None, base, str(dest), project_dir=str(dest.parent))
    assert captured and captured[0][0] == base
    assert captured[0][1:3] == ["-m", "venv"]
    # R189: create runs at the final destination (not staging rename).
    assert Path(captured[0][-1]).resolve() == dest.resolve()
    assert dest.is_dir()
    assert Path(out).resolve().is_relative_to(dest.resolve()) or str(dest) in str(Path(out).resolve())
    assert Path(out).name.startswith("python")
    assert not any(dest.parent.glob(".cdm-venv-bak-*"))
    assert not any(dest.parent.glob(".cdm-venv-stage-*"))


def test_create_venv_with_progress_refuses_unsafe_destination(qapp_ready, tmp_path, monkeypatch):
    """C01 gap: destination guard must run before QProcess, not only in sync create."""
    from ui import venvprocess as vp

    def boom(*_a, **_k):
        raise AssertionError("QProcess must not start for unsafe destination")

    monkeypatch.setattr(vp, "run_argv_with_progress", boom)
    with pytest.raises(RuntimeError, match="IDE environment|outside|project root|empty"):
        vp.create_venv_with_progress(None, sys.executable, sys.prefix, project_dir=str(tmp_path))
