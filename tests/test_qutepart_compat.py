# -*- coding: utf-8 -*-
"""Tests for qutepart / PyQt5 drawLine float coercion."""

import importlib.util
import os
import subprocess
import sys
import textwrap

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


def test_int_coords_helper():
    compat = _load_compat()
    assert compat.int_coords(1, 1.5, 10, 2.9) == (1, 1, 10, 2)


def test_int_draw_line_args_preserves_non_numeric_overloads():
    """QLine / QPoint overloads must pass through unchanged."""
    compat = _load_compat()
    sentinel = object()
    assert compat.int_draw_line_args((sentinel,)) == (sentinel,)
    assert compat.int_draw_line_args((1, 2)) == (1, 2)


def test_qpainter_drawline_monkeypatch_breaks_qlinef_after_restore():
    """Regression: do not patch QPainter.drawLine (breaks flow UI painting).

    Runs in a subprocess so the sip break does not poison this pytest process.
    """
    script = textwrap.dedent(
        r"""
        from PyQt5.QtCore import QLineF, Qt
        from PyQt5.QtGui import QImage, QPainter

        img = QImage(20, 20, QImage.Format_RGB32)
        img.fill(Qt.white)
        line = QLineF(1.0, 1.0, 10.0, 10.0)
        original = QPainter.drawLine

        def _safe(painter, *args):
            if len(args) == 4:
                args = tuple(int(v) for v in args)
            return original(painter, *args)

        QPainter.drawLine = _safe
        QPainter.drawLine = original
        painter = QPainter(img)
        try:
            painter.drawLine(line)
        except TypeError:
            raise SystemExit(0)
        finally:
            painter.end()
        raise SystemExit(1)
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
