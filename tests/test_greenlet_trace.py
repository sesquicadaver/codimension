# -*- coding: utf-8 -*-
"""Tests for greenlet-aware debugger thread bookkeeping."""

import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THREAD_UTILS_PATH = os.path.join(ROOT, "codimension", "debugger", "client", "threadutils_cdm_dbg.py")


def _load_thread_utils():
    """Load threadutils without the debugger client import chain."""
    spec = importlib.util.spec_from_file_location(
        "threadutils_cdm_dbg",
        THREAD_UTILS_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["threadutils_cdm_dbg"] = module
    spec.loader.exec_module(module)
    return module


class _FakeThread:
    def __init__(self, is_greenlet=False):
        self.isGreenlet = is_greenlet


def test_filter_active_threads_drops_finished_os_threads():
    """Non-greenlet debugger threads disappear when the OS thread exits."""
    mod = _load_thread_utils()
    threads = {1: _FakeThread(), 2: _FakeThread()}
    filtered = mod.filter_active_threads(threads, {1}, keep_greenlets=False)
    assert set(filtered.keys()) == {1}


def test_filter_active_threads_keeps_greenlets():
    """Greenlet contexts stay registered even without a matching OS thread id."""
    mod = _load_thread_utils()
    threads = {100: _FakeThread(is_greenlet=True), 1: _FakeThread()}
    filtered = mod.filter_active_threads(threads, {1}, keep_greenlets=True)
    assert set(filtered.keys()) == {1, 100}
