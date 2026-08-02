# -*- coding: utf-8 -*-
"""T110: chrome stubs must cover MainWindowDebuggerMixin.switchDebugMode attrs."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MIXIN_PATH = ROOT / "codimension" / "ui" / "mainwindow_debug.py"


def _attrs_used_in_switch_debug_mode() -> set[str]:
    """Collect ``self.<name>`` attribute loads inside ``switchDebugMode``."""
    tree = ast.parse(MIXIN_PATH.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "MainWindowDebuggerMixin":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "switchDebugMode":
                    names: set[str] = set()
                    for child in ast.walk(item):
                        if (
                            isinstance(child, ast.Attribute)
                            and isinstance(child.value, ast.Name)
                            and child.value.id == "self"
                        ):
                            names.add(child.attr)
                    return names
    raise AssertionError("switchDebugMode not found on MainWindowDebuggerMixin")


@pytest.mark.debugger_session
def test_mixin_host_provides_switch_debug_mode_chrome():
    """Every self.* attribute read in switchDebugMode exists on MixinDebuggerHost."""
    from .host import create_mixin_host

    required = _attrs_used_in_switch_debug_mode()
    # Methods implemented on the host / mixin itself are fine if callable.
    host = create_mixin_host()
    missing = [name for name in sorted(required) if not hasattr(host, name)]
    assert not missing, f"MixinDebuggerHost missing chrome for switchDebugMode: {missing}"
