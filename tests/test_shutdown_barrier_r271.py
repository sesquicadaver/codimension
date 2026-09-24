# -*- coding: utf-8 -*-
"""R271: BackgroundTaskRegistry quiescence barrier."""

from __future__ import annotations

import threading
import time

from codimension.utils.background_task_registry import (
    BackgroundTaskRegistry,
    get_background_task_registry,
)


def test_r271_registry_wait_all_idle() -> None:
    reg = BackgroundTaskRegistry()
    flags = {"active": False}

    reg.register(
        "idle",
        cancel=lambda: None,
        wait=lambda _ms: True,
        is_active=lambda: flags["active"],
    )
    assert reg.active_tasks() == []
    assert reg.wait_all(timeout_ms=100) is True
    assert reg.dump_state()["registered"] == ["idle"]


def test_r271_registry_cancel_then_wait() -> None:
    reg = BackgroundTaskRegistry()
    state = {"active": True, "cancelled": False}
    release = threading.Event()

    def cancel() -> None:
        state["cancelled"] = True
        release.set()

    def wait(timeout_ms: int) -> bool:
        release.wait(timeout_ms / 1000.0)
        state["active"] = False
        return True

    reg.register("worker", cancel=cancel, wait=wait, is_active=lambda: state["active"])
    assert reg.active_tasks() == ["worker"]
    reg.request_shutdown()
    assert state["cancelled"] is True
    assert reg.wait_all(timeout_ms=1000) is True
    assert reg.active_tasks() == []


def test_r271_registry_wait_timeout() -> None:
    reg = BackgroundTaskRegistry()
    reg.register(
        "stuck",
        cancel=lambda: None,
        wait=lambda ms: time.sleep(ms / 1000.0) or False,
        is_active=lambda: True,
    )
    assert reg.wait_all(timeout_ms=50) is False
    assert reg.active_tasks() == ["stuck"]


def test_r271_singleton_reset_for_tests() -> None:
    reg = get_background_task_registry()
    reg.reset_for_tests()
    assert reg.active_tasks() == []
    reg.register(
        "tmp",
        cancel=lambda: None,
        wait=lambda _ms: True,
        is_active=lambda: False,
    )
    assert "tmp" in reg.dump_state()["registered"]
    reg.reset_for_tests()
    assert reg.dump_state()["registered"] == []
