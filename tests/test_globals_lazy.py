# -*- coding: utf-8 -*-
"""T084: GlobalData must not construct at import time."""

from __future__ import annotations

import ast
from pathlib import Path


def test_globals_source_has_lazy_singleton() -> None:
    """Source contract: no eager GlobalDataWrapper() at module level."""
    path = Path(__file__).resolve().parents[1] / "codimension" / "utils" / "globals.py"
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    # Forbid module-level GlobalDataWrapper() call
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if isinstance(node.value, ast.Call):
                func = node.value.func
                if isinstance(func, ast.Name) and func.id == "GlobalDataWrapper":
                    raise AssertionError("eager GlobalDataWrapper() at module level")
    assert "_globals_singleton" in text
    assert "def resetGlobalDataForTests" in text
    assert "if _globals_singleton is None" in text


def test_mainwindow_uses_mro_not_extendinstance() -> None:
    """T083: CodimensionMainWindow declares mixins in the class bases."""
    text = Path("codimension/ui/mainwindow.py").read_text(encoding="utf-8")
    assert "extendInstance" not in text
    assert "MainWindowDebuggerMixin" in text
    assert "class CodimensionMainWindow(" in text
    debug = Path("codimension/ui/mainwindow_debug.py").read_text(encoding="utf-8")
    assert "class MainWindowDebuggerMixin" in debug
