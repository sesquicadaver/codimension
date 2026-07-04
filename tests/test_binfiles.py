# -*- coding: utf-8 -*-
"""Tests for codimension.utils.binfiles.getHexdump (no full IDE import chain)."""

import importlib.util
import os
import sys
import tempfile
import types
from unittest.mock import MagicMock, patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UTILS_DIR = os.path.join(ROOT, "codimension", "utils")
_BINFILES_PATH = os.path.join(UTILS_DIR, "binfiles.py")


def _load_binfiles_module(hexdump_available=True):
    """Load binfiles in isolation with mocked utils.globals."""
    mock_wrapper = MagicMock()
    mock_wrapper.hexdumpAvailable = hexdump_available

    utils_pkg = types.ModuleType("utils")
    utils_pkg.__path__ = [UTILS_DIR]
    sys.modules["utils"] = utils_pkg

    globals_mod = types.ModuleType("utils.globals")
    globals_mod.GlobalData = lambda: mock_wrapper
    sys.modules["utils.globals"] = globals_mod

    spec = importlib.util.spec_from_file_location("utils.binfiles", _BINFILES_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["utils.binfiles"] = module
    spec.loader.exec_module(module)
    return module


def test_get_hexdump_unavailable():
    """Returns None when hexdump binary is not available."""
    mod = _load_binfiles_module(hexdump_available=False)
    assert mod.getHexdump("/tmp/x") is None


def test_get_hexdump_missing_file():
    """Returns None for non-existent file."""
    mod = _load_binfiles_module(hexdump_available=True)
    assert mod.getHexdump("/nonexistent/file.bin") is None


def test_get_hexdump_success():
    """Runs hexdump -C via subprocess when available."""
    mod = _load_binfiles_module(hexdump_available=True)
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(b"\x00\x01\x02")
        path = tmp.name
    try:
        fake = MagicMock(returncode=0, stdout="00000000  00 01 02\n", stderr="")
        with patch.object(mod.subprocess, "run", return_value=fake) as run_mock:
            result = mod.getHexdump(path)
        assert result == "00000000  00 01 02\n"
        run_mock.assert_called_once()
        assert run_mock.call_args[0][0] == ["hexdump", "-C", path]
    finally:
        os.remove(path)


def test_get_hexdump_subprocess_failure():
    """Returns None when hexdump exits non-zero."""
    mod = _load_binfiles_module(hexdump_available=True)
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        path = tmp.name
    try:
        fake = MagicMock(returncode=1, stdout="", stderr="error")
        with patch.object(mod.subprocess, "run", return_value=fake):
            assert mod.getHexdump(path) is None
    finally:
        os.remove(path)
