# -*- coding: utf-8 -*-
"""T070: originalSysPath must be a copy, not an alias of sys.path."""

from __future__ import annotations

import sys
from pathlib import Path


def test_codimension_entrypoint_uses_list_copy() -> None:
    """Entrypoint source must assign originalSysPath via list(sys.path)."""
    root = Path(__file__).resolve().parents[1]
    text = (root / "codimension" / "codimension.py").read_text(encoding="utf-8")
    assert "originalSysPath = list(sys.path)" in text


def test_list_copy_breaks_sys_path_aliasing() -> None:
    """Behavioral contract: mutating the copy must not mutate sys.path."""
    before = list(sys.path)
    original = list(sys.path)
    assert id(original) != id(sys.path)
    original.insert(0, "__cdm_t070_marker__")
    assert sys.path == before
    assert "__cdm_t070_marker__" not in sys.path
