# -*- coding: utf-8 -*-
"""Tests for qutepart / PyQt5 drawLine float coercion."""

import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPAT_PATH = os.path.join(ROOT, "codimension", "editor", "qutepart_compat.py")


def _load_compat():
    """Load qutepart_compat without the full IDE dependency chain."""
    spec = importlib.util.spec_from_file_location("qutepart_compat", COMPAT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_int_draw_line_args_coerces_floats():
    """Whitespace middleHeight floats must become ints for QPainter.drawLine."""
    compat = _load_compat()
    assert compat.int_draw_line_args((1, 1.5, 10, 2.9)) == (1, 1, 10, 2)


def test_int_draw_line_args_preserves_non_numeric_overloads():
    """QLine / QPoint overloads must pass through unchanged."""
    compat = _load_compat()
    sentinel = object()
    assert compat.int_draw_line_args((sentinel,)) == (sentinel,)
    assert compat.int_draw_line_args((1, 2)) == (1, 2)
