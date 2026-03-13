# -*- coding: utf-8 -*-
"""Tests for cdmplugins.todopanel.todoscanner.

Per-plugin smoke tests (plan section 6.1). No Qt/GUI required.
Import todoscanner directly to avoid pulling in WizardInterface/Qt.
"""

import importlib.util
import os.path
import tempfile

import pytest

# Load todoscanner without todopanel __init__ (which requires Qt)
_spec = importlib.util.spec_from_file_location(
    "todoscanner",
    os.path.join(os.path.dirname(__file__), "..", "cdmplugins", "todopanel", "todoscanner.py"),
)
_todoscanner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_todoscanner)

scan_directory = _todoscanner.scan_directory
scan_file = _todoscanner.scan_file
scan_single_file = _todoscanner.scan_single_file


def test_scan_file_empty():
    """Empty file returns no results."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("")
    try:
        assert scan_file(f.name) == []
    finally:
        os.unlink(f.name)


def test_scan_file_todo():
    """File with TODO returns result."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("x = 1  # TODO: fix this\n")
        f.write("y = 2  # FIXME: check\n")
    try:
        results = scan_file(f.name)
        assert len(results) == 2
        assert results[0]["line"] == 1
        assert results[0]["tag"] == "TODO"
        assert "fix this" in results[0]["text"]
        assert results[1]["tag"] == "FIXME"
    finally:
        os.unlink(f.name)


def test_scan_file_nonexistent():
    """Nonexistent file returns empty."""
    assert scan_file("/nonexistent/path/file.py") == []


def test_scan_single_file_empty_path():
    """Empty path returns empty."""
    assert scan_single_file("") == []
    assert scan_single_file(None) == []


def test_scan_directory_empty():
    """Empty or nonexistent directory returns empty."""
    assert scan_directory("") == []
    assert scan_directory(None) == []
    assert scan_directory("/nonexistent/dir") == []


def test_scan_directory_finds_todo():
    """Directory scan finds TODO in Python files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pyfile = os.path.join(tmpdir, "test.py")
        with open(pyfile, "w") as f:
            f.write("# TODO: implement\n")
        results = scan_directory(tmpdir)
        assert len(results) == 1
        assert results[0]["tag"] == "TODO"
        assert results[0]["file"] == pyfile
