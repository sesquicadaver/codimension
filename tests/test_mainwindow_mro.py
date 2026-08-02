# -*- coding: utf-8 -*-
"""T083: MainWindow MRO / debugger mixin source contracts."""

from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def test_mainwindow_declares_mixin_bases() -> None:
    """CodimensionMainWindow must list mixins in the class statement (no extendInstance)."""
    text = (_ROOT / "codimension" / "ui" / "mainwindow.py").read_text(encoding="utf-8")
    assert "extendInstance" not in text
    tree = ast.parse(text)
    found = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "CodimensionMainWindow":
            found = node
            break
    assert found is not None
    base_names = []
    for base in found.bases:
        if isinstance(base, ast.Name):
            base_names.append(base.id)
    assert "QMainWindow" in base_names
    assert "MainWindowDebuggerMixin" in base_names
    assert "MainWindowStatusBarMixin" in base_names
    assert "MainWindowMenuMixin" in base_names
    assert "MainWindowRedirectedIOMixin" in base_names


def test_debugger_mixin_defines_session_api() -> None:
    """Extracted mixin must expose the session control surface."""
    text = (_ROOT / "codimension" / "ui" / "mainwindow_debug.py").read_text(encoding="utf-8")
    tree = ast.parse(text)
    methods = set()
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "MainWindowDebuggerMixin":
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    methods.add(item.name)
    for name in (
        "switchDebugMode",
        "_onDbgGo",
        "_onDbgNext",
        "_onStopDbgSession",
        "setRunToLineButtonState",
        "_onDebuggerStateChanged",
    ):
        assert name in methods, name
