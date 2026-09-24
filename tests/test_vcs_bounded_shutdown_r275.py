# -*- coding: utf-8 -*-
"""R275: VCS plugin thread shutdown uses a bounded wait."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("PyQt5")

from plugins.vcssupport import vcsmanager as vcsmanager_mod  # noqa: E402
from plugins.vcssupport.vcsmanager import VCSPluginDescriptor  # noqa: E402


def test_r275_stop_thread_timeout_returns_false_and_does_not_block(monkeypatch) -> None:
    """Hung VCS thread must not block dismiss forever."""

    class _StuckThread:
        def __init__(self) -> None:
            self.stopped = False
            self.cleared = False
            self.wait_ms = None

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
    from pathlib import Path

    text = Path(vcsmanager_mod.__file__).read_text(encoding="utf-8")
    assert "self.thread.wait()" not in text
    assert "timeout_ms" in text
    assert "R275" in text
