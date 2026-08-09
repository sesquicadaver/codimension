# -*- coding: utf-8 -*-
"""R177: parse_log_location unit tests."""

from __future__ import annotations

from pathlib import Path

from utils.log_location import parse_log_location


def test_colon_format_existing(tmp_path: Path):
    py = tmp_path / "mod.py"
    py.write_text("x = 1\n", encoding="utf-8")
    path = str(py)
    msg = f"WARNING  … {path}:12: Could not resolve 'import numpy' at line 12"
    assert parse_log_location(msg) == (path, 12)


def test_colon_format_space_separator(tmp_path: Path):
    py = tmp_path / "a.py"
    py.write_text("", encoding="utf-8")
    path = str(py)
    assert parse_log_location(f"{path}:3 more text") == (path, 3)


def test_traceback_format(tmp_path: Path):
    py = tmp_path / "tb.py"
    py.write_text("", encoding="utf-8")
    path = str(py)
    assert parse_log_location(f'File "{path}", line 7, in main') == (path, 7)


def test_parens_format(tmp_path: Path):
    py = tmp_path / "p.py"
    py.write_text("", encoding="utf-8")
    path = str(py)
    assert parse_log_location(f"{path}(9): unused") == (path, 9)


def test_missing_file_returns_none(tmp_path: Path):
    missing = tmp_path / "gone.py"
    assert parse_log_location(f"{missing}:1: msg") is None


def test_require_existing_false(tmp_path: Path):
    missing = str(tmp_path / "gone.py")
    assert parse_log_location(f"{missing}:4: msg", require_existing=False) == (missing, 4)


def test_no_location():
    assert parse_log_location("WARNING Unresolved imports: numpy") is None
    assert parse_log_location("") is None


def test_line_must_be_positive(tmp_path: Path):
    py = tmp_path / "z.py"
    py.write_text("", encoding="utf-8")
    assert parse_log_location(f"{py}:0: bad") is None
