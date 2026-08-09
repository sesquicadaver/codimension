# -*- coding: utf-8 -*-
#
# codimension - safe-mode startup (R175)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Safe-mode startup: skip plugins and flow overlays (R175).

Enable with ``--safe-mode`` or environment ``CDM_SAFE_MODE=1`` (truthy).
Qt-free; UI/startup code consults :func:`is_safe_mode_enabled`.
"""

from __future__ import annotations

import os
from typing import Mapping, Optional

#: Environment variable that enables safe mode (default: off).
SAFE_MODE_ENV = "CDM_SAFE_MODE"

_TRUTHY = frozenset({"1", "true", "yes", "on"})

#: Set when the process was started with ``--safe-mode``.
_cli_requested: bool = False


def parse_truthy(value: object) -> bool:
    """Interpret common truthy strings; everything else is False."""
    return str(value).strip().lower() in _TRUTHY


def activate_safe_mode_from_cli() -> None:
    """Mark safe mode as requested by the command line (process-wide)."""
    global _cli_requested
    _cli_requested = True


def reset_safe_mode_for_tests() -> None:
    """Clear the CLI latch (tests only)."""
    global _cli_requested
    _cli_requested = False


def is_safe_mode_enabled(environ: Optional[Mapping[str, str]] = None) -> bool:
    """Return True when safe mode is active (CLI latch or env override).

    When ``environ`` is passed explicitly, only that mapping is consulted for
    the env key (plus the CLI latch) — keeps unit tests isolated from the
    real process environment.
    """
    if _cli_requested:
        return True
    env: Mapping[str, str] = os.environ if environ is None else environ
    if SAFE_MODE_ENV not in env:
        return False
    raw = env.get(SAFE_MODE_ENV, "")
    if raw is None or str(raw).strip() == "":
        return False
    return parse_truthy(raw)


def safe_mode_reason(environ: Optional[Mapping[str, str]] = None) -> Optional[str]:
    """Human-readable reason when safe mode is on, else ``None``."""
    if not is_safe_mode_enabled(environ):
        return None
    if _cli_requested:
        return "CLI --safe-mode"
    return f"env {SAFE_MODE_ENV}"


__all__ = [
    "SAFE_MODE_ENV",
    "activate_safe_mode_from_cli",
    "is_safe_mode_enabled",
    "parse_truthy",
    "reset_safe_mode_for_tests",
    "safe_mode_reason",
]
