# -*- coding: utf-8 -*-
"""Bypass tests for T085 core import-graph gate."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "scripts" / "check_core_import_graph.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_core_import_graph", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_t085_flags_absolute_and_package_ui() -> None:
    gate = _load()
    assert gate._is_forbidden("ui.qt")
    assert gate._is_forbidden("codimension.ui.qt")
    assert gate._is_forbidden("codimension.editor.texteditor")
    assert not gate._is_forbidden("codimension.parsers.brief_ast")
    assert not gate._is_forbidden("codimension.utils.project_scan")


def test_t085_flags_relative_ui_import(tmp_path: Path) -> None:
    """from ..ui import qt must resolve to codimension.ui.qt and fail the gate."""
    gate = _load()
    core_dir = _ROOT / "codimension" / "core"
    evil = core_dir / "_t085_rel_probe.py"
    try:
        evil.write_text("from ..ui import qt\n", encoding="utf-8")
        failures = gate.check_file(evil)
        assert failures, "relative ..ui import must be rejected"
        assert "codimension.ui" in failures[0]
    finally:
        if evil.exists():
            evil.unlink()


def test_t085_flags_relative_import_ui_name() -> None:
    """from .. import ui must resolve to codimension.ui and fail the gate."""
    gate = _load()
    core_dir = _ROOT / "codimension" / "core"
    evil = core_dir / "_t085_rel_probe2.py"
    try:
        evil.write_text("from .. import ui\n", encoding="utf-8")
        failures = gate.check_file(evil)
        assert failures, "from .. import ui must be rejected"
        assert any("codimension.ui" in f for f in failures)
    finally:
        if evil.exists():
            evil.unlink()


def test_t085_flags_importlib_dynamic() -> None:
    """importlib.import_module('codimension.ui') must fail the gate."""
    gate = _load()
    core_dir = _ROOT / "codimension" / "core"
    evil = core_dir / "_t085_dyn_probe.py"
    try:
        evil.write_text(
            "import importlib\nimportlib.import_module('codimension.ui')\n",
            encoding="utf-8",
        )
        failures = gate.check_file(evil)
        assert failures, "dynamic import_module must be rejected"
        assert any("codimension.ui" in f for f in failures)
    finally:
        if evil.exists():
            evil.unlink()


def test_r100_importutils_is_scanned_and_qt_free() -> None:
    """R100: utils.importutils is in the Qt-free gate and has no ui.qt edge."""
    gate = _load()
    target = _ROOT / "codimension" / "utils" / "importutils.py"
    assert target in gate.QTFREE_UTILS_FILES
    assert gate.check_file(target) == []
    rc = gate.main()
    assert rc == 0
