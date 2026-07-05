# -*- coding: utf-8 -*-
"""Tests for debugger watchpoint utilities and model."""

import importlib.util
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODMENSION_DIR = os.path.join(ROOT, "codimension")
DEBUGGER_DIR = os.path.join(CODMENSION_DIR, "debugger")


def _load_wputils():
    """Load wputils without importing the debugger package."""
    spec = importlib.util.spec_from_file_location(
        "debugger.wputils",
        os.path.join(DEBUGGER_DIR, "wputils.py"),
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["debugger.wputils"] = module
    spec.loader.exec_module(module)
    return module


def _load_watchpoint_model():
    """Load WatchPointModel with a minimal ui.qt stub."""
    ui_pkg = types.ModuleType("ui")
    ui_pkg.__path__ = [os.path.join(CODMENSION_DIR, "ui")]
    sys.modules["ui"] = ui_pkg

    qt_mod = types.ModuleType("ui.qt")
    from PyQt5.QtCore import QAbstractItemModel, QModelIndex, Qt, pyqtSignal

    qt_mod.QAbstractItemModel = QAbstractItemModel
    qt_mod.QModelIndex = QModelIndex
    qt_mod.Qt = Qt
    qt_mod.pyqtSignal = pyqtSignal
    sys.modules["ui.qt"] = qt_mod

    debugger_pkg = types.ModuleType("debugger")
    debugger_pkg.__path__ = [DEBUGGER_DIR]
    sys.modules["debugger"] = debugger_pkg

    spec = importlib.util.spec_from_file_location(
        "debugger.watchpointmodel",
        os.path.join(DEBUGGER_DIR, "watchpointmodel.py"),
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["debugger.watchpointmodel"] = module
    spec.loader.exec_module(module)
    return module


def test_format_remote_watch_condition_plain():
    """Plain expressions are sent unchanged."""
    wputils = _load_wputils()
    assert wputils.formatRemoteWatchCondition("len(x) > 0", "") == "len(x) > 0"


def test_format_remote_watch_condition_changed_flag():
    """Changed/created flags are appended for the debuggee."""
    wputils = _load_wputils()
    assert wputils.formatRemoteWatchCondition("obj", "??changed??") == "obj ??changed??"
    assert wputils.formatRemoteWatchCondition("obj", "??created??") == "obj ??created??"


def test_parse_remote_watch_condition_roundtrip():
    """Remote condition parsing reverses formatting."""
    wputils = _load_wputils()
    remote = wputils.formatRemoteWatchCondition("value", "??created??")
    cond, special = wputils.parseRemoteWatchCondition(remote)
    assert cond == "value"
    assert special == "??created??"


def test_watchpoint_model_add_and_lookup():
    """WatchPointModel stores and finds expressions by condition and trigger."""
    model_mod = _load_watchpoint_model()
    model = model_mod.WatchPointModel()
    model.addWatchPoint("x > 1", "??changed??", (False, True, 2))
    idx = model.getWatchPointIndex("x > 1", "??changed??")
    assert idx.isValid()
    assert model.getWatchPointByIndex(idx)[:5] == ["x > 1", "??changed??", False, True, 2]


def test_watchpoint_model_find_by_remote_condition():
    """Remote wire conditions resolve back to model rows."""
    model_mod = _load_watchpoint_model()
    wputils = _load_wputils()
    model = model_mod.WatchPointModel()
    model.addWatchPoint("obj", "??created??", (True, True, 0))
    remote = wputils.formatRemoteWatchCondition("obj", "??created??")
    idx = model.findWatchPointIndexByRemoteCondition(remote)
    assert idx.isValid()
