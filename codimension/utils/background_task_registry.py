# -*- coding: utf-8 -*-
#
# codimension - central background-task quiescence registry (R271)
# Copyright (C) 2026  Codimension Team
# The license is described in the LICENSE file at the root directory.
#

"""Register cancel/wait probes so IDE close can wait for quiescence.

R271: ``MainWindow.closeEvent`` must not proceed to forced ``gc.collect`` /
QObject teardown until :meth:`BackgroundTaskRegistry.wait_all` reports no
active tasks (AI workers, project scans, …).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BackgroundTaskHandle:
    """One named background subsystem participating in shutdown."""

    name: str
    cancel: Callable[[], None]
    wait: Callable[[int], bool]
    is_active: Callable[[], bool]


class BackgroundTaskRegistry:
    """Thread-safe registry of cancel/wait probes for IDE shutdown (R271)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tasks: dict[str, BackgroundTaskHandle] = {}
        self._shutdown_requested = False

    def register(
        self,
        name: str,
        *,
        cancel: Callable[[], None],
        wait: Callable[[int], bool],
        is_active: Callable[[], bool],
    ) -> None:
        """Register or replace a named background task probe."""
        key = (name or "").strip()
        if not key:
            raise ValueError("Background task name must be non-empty")
        handle = BackgroundTaskHandle(name=key, cancel=cancel, wait=wait, is_active=is_active)
        with self._lock:
            self._tasks[key] = handle

    def unregister(self, name: str) -> None:
        """Remove a previously registered probe (idempotent)."""
        with self._lock:
            self._tasks.pop(name, None)

    def request_shutdown(self) -> None:
        """Ask every registered subsystem to cancel cooperative work."""
        with self._lock:
            self._shutdown_requested = True
            handles = list(self._tasks.values())
        for handle in handles:
            try:
                handle.cancel()
            except Exception:
                logging.warning("Background task cancel failed: %s", handle.name, exc_info=True)

    def wait_all(self, timeout_ms: int = 5000) -> bool:
        """Wait until every registered task reports inactive.

        Returns ``True`` when :meth:`active_tasks` is empty after the waits.
        Budget is shared across tasks in registration order.
        """
        remaining_ms = max(0, int(timeout_ms))
        with self._lock:
            handles = list(self._tasks.values())
        for handle in handles:
            try:
                if not handle.is_active():
                    continue
            except Exception:
                logging.warning("Background task is_active failed: %s", handle.name, exc_info=True)
                continue
            if remaining_ms <= 0:
                break
            started = time.monotonic()
            try:
                handle.wait(remaining_ms)
            except Exception:
                logging.warning("Background task wait failed: %s", handle.name, exc_info=True)
            elapsed_ms = int((time.monotonic() - started) * 1000)
            remaining_ms = max(0, remaining_ms - max(elapsed_ms, 0))
        return not self.active_tasks()

    def active_tasks(self) -> list[str]:
        """Names of registered subsystems that still report active work."""
        with self._lock:
            handles = list(self._tasks.values())
        active: list[str] = []
        for handle in handles:
            try:
                if handle.is_active():
                    active.append(handle.name)
            except Exception:
                logging.warning("Background task is_active failed: %s", handle.name, exc_info=True)
                active.append(handle.name)
        return active

    def dump_state(self) -> dict[str, Any]:
        """Structured snapshot for crash/lifecycle telemetry (R271 / R273)."""
        with self._lock:
            names = sorted(self._tasks)
            shutdown = self._shutdown_requested
        return {
            "shutdown_requested": shutdown,
            "registered": names,
            "active": self.active_tasks(),
        }

    def reset_for_tests(self) -> None:
        """Clear all registrations (unit tests only)."""
        with self._lock:
            self._tasks.clear()
            self._shutdown_requested = False


_REGISTRY = BackgroundTaskRegistry()


def get_background_task_registry() -> BackgroundTaskRegistry:
    """Process-wide registry singleton used by MainWindow shutdown."""
    return _REGISTRY
