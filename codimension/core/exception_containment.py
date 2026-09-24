# -*- coding: utf-8 -*-
#
# codimension - exception containment policy (R272)
# Copyright (C) 2026  Codimension Team
# The license is described in the LICENSE file at the root directory.
#

"""Classify uncaught exceptions as process-fatal vs recoverable (R272).

Once the IDE GUI is up, most callback exceptions must be contained (logged /
reported) without ``application.exit(1)``. Process exit remains only for
explicitly classified unrecoverable failures and pre-GUI bootstrap errors.
"""

from __future__ import annotations

from typing import Type


class UnrecoverableError(BaseException):
    """Marker for invariants that must terminate the process (R272).

    Subclasses :class:`BaseException` (not :class:`Exception`) so generic
    ``except Exception`` handlers cannot accidentally swallow it.
    """


# Explicitly fatal built-ins once the GUI is running. Everything else that is
# a normal :class:`Exception` is treated as recoverable callback noise.
_FATAL_WHEN_READY: tuple[Type[BaseException], ...] = (
    MemoryError,
    SystemError,
    RecursionError,
)


def is_process_fatal(
    exc_type: Type[BaseException] | None,
    *,
    application_ready: bool,
) -> bool:
    """Return True when the global hook must terminate the IDE process.

    Parameters
    ----------
    exc_type:
        Exception type passed to ``sys.excepthook``.
    application_ready:
        True when both ``QApplication`` and the main window exist. Before that,
        uncaught errors still abort startup (return code path / exit).
    """
    if exc_type is None:
        return True
    if not isinstance(exc_type, type) or not issubclass(exc_type, BaseException):
        return True
    # KeyboardInterrupt has a dedicated quit path in the hook; never fatal here.
    if issubclass(exc_type, KeyboardInterrupt):
        return False
    # Non-Exception BaseExceptions (SystemExit, UnrecoverableError, …) stay fatal.
    if not issubclass(exc_type, Exception):
        return True
    if issubclass(exc_type, _FATAL_WHEN_READY):
        return True
    if not application_ready:
        # Bootstrap / pre-GUI failures remain process-stopping.
        return True
    # R272: Qt/plugin/timer/editor callback exceptions stay contained.
    return False


def classify_uncaught(
    exc_type: Type[BaseException] | None,
    *,
    application_ready: bool,
) -> str:
    """Human-readable label for logs: ``fatal``, ``recoverable``, or ``interrupt``."""
    if exc_type is not None and issubclass(exc_type, KeyboardInterrupt):
        return "interrupt"
    if is_process_fatal(exc_type, application_ready=application_ready):
        return "fatal"
    return "recoverable"
