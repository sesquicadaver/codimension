# -*- coding: utf-8 -*-
"""R275: VCS plugin thread shutdown uses a bounded wait."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("PyQt5")

_ROOT = Path(__file__).resolve().parents[1]
_CODIM = _ROOT / "codimension"
_VCSMANAGER_PATH = _CODIM / "plugins" / "vcssupport" / "vcsmanager.py"


def _purge_incomplete_stubs(*prefixes: str) -> None:
    """Drop non-codimension stubs left by earlier test modules during collection."""
    dirty = False
    for name in list(sys.modules):
        if not any(name == p or name.startswith(p + ".") for p in prefixes):
            continue
        mod = sys.modules.get(name)
        if mod is None:
            continue
        file_name = (getattr(mod, "__file__", None) or "").replace("\\", "/")
        if "codimension/" not in file_name:
            del sys.modules[name]
            dirty = True
    if dirty:
        importlib.invalidate_caches()


def _load_vcsmanager():
    """Import real vcssupport.vcsmanager after clearing collection-time stubs."""
    _purge_incomplete_stubs("utils", "ui", "plugins")
    if str(_CODIM) not in sys.path:
        sys.path.insert(0, str(_CODIM))
    # Force a fresh load so a prior failed/partial import cannot mask stubs.
    for name in list(sys.modules):
        if name == "plugins.vcssupport.vcsmanager" or name.startswith("plugins.vcssupport.vcsmanager."):
            del sys.modules[name]
    from plugins.vcssupport import vcsmanager as vcsmanager_mod
    from plugins.vcssupport.vcsmanager import VCSPluginDescriptor

    return vcsmanager_mod, VCSPluginDescriptor


def test_r275_stop_thread_timeout_returns_false_and_does_not_block(monkeypatch) -> None:
    """Hung VCS thread must not block dismiss forever."""
    vcsmanager_mod, VCSPluginDescriptor = _load_vcsmanager()

    class _StuckThread:
        def __init__(self) -> None:
            self.stopped = False
            self.cleared = False
            self.wait_ms: int | None = None

        def clearRequestQueue(self) -> None:
            self.cleared = True

        def stop(self) -> None:
            self.stopped = True

        def wait(self, ms: int) -> bool:
            self.wait_ms = ms
            return False

        def isRunning(self) -> bool:
            return True

    stuck = _StuckThread()
    descriptor = VCSPluginDescriptor.__new__(VCSPluginDescriptor)
    descriptor.manager = None
    descriptor.pluginID = 0
    descriptor.plugin = SimpleNamespace(getName=lambda: "stub-vcs")
    descriptor.thread = stuck
    descriptor.indicators = {}

    notes: list[str] = []
    monkeypatch.setattr(vcsmanager_mod, "_note_lifecycle", lambda ev, detail="": notes.append(f"{ev}:{detail}"))

    assert descriptor.stopThread(timeout_ms=100) is False
    assert stuck.stopped is True
    assert stuck.cleared is True
    assert stuck.wait_ms == 100
    assert any(n.startswith("vcs_shutdown_degraded:") for n in notes)


def test_r275_stop_thread_success() -> None:
    _, VCSPluginDescriptor = _load_vcsmanager()

    class _OkThread:
        def clearRequestQueue(self) -> None:
            return None

        def stop(self) -> None:
            return None

        def wait(self, ms: int) -> bool:
            del ms
            return True

        def isRunning(self) -> bool:
            return False

    descriptor = VCSPluginDescriptor.__new__(VCSPluginDescriptor)
    descriptor.plugin = SimpleNamespace(getName=lambda: "ok-vcs")
    descriptor.thread = _OkThread()
    assert descriptor.stopThread(timeout_ms=50) is True


def test_r275_source_has_no_unbounded_wait() -> None:
    text = _VCSMANAGER_PATH.read_text(encoding="utf-8")
    assert "self.thread.wait()" not in text
    assert "timeout_ms" in text
    assert "R275" in text
