# -*- coding: utf-8 -*-
#
# codimension - package version / release channel (R171)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Single version string plus a release-channel label (R171).

Still one version (no multi-branch promotion). Channel is metadata for About /
future update checks (R172+). Override at runtime with ``CDM_RELEASE_CHANNEL``.
"""

from __future__ import annotations

import os
from typing import Mapping, Optional

version = "4.11.0"

#: Allowed channel labels (stable packaging / beta / tip-of-tree).
VALID_RELEASE_CHANNELS: frozenset[str] = frozenset({"stable", "beta", "dev"})

#: Default channel baked into the package (still one ``version`` string).
release_channel = "stable"

#: Environment override for local / CI builds (does not change ``version``).
RELEASE_CHANNEL_ENV = "CDM_RELEASE_CHANNEL"


def normalize_release_channel(value: Optional[str], *, default: str = "stable") -> str:
    """Return a valid channel label; unknown values fall back to ``default``."""
    raw = (value or "").strip().lower()
    if raw in VALID_RELEASE_CHANNELS:
        return raw
    fallback = (default or "stable").strip().lower()
    if fallback in VALID_RELEASE_CHANNELS:
        return fallback
    return "stable"


def get_release_channel(environ: Optional[Mapping[str, str]] = None) -> str:
    """Resolve the effective release channel (env override, then module default)."""
    env: Mapping[str, str] = os.environ if environ is None else environ
    override = env.get(RELEASE_CHANNEL_ENV)
    if override is not None and str(override).strip():
        return normalize_release_channel(str(override))
    return normalize_release_channel(release_channel)


def version_with_channel(environ: Optional[Mapping[str, str]] = None) -> str:
    """Return a display string like ``4.11.0 (stable)``."""
    return f"{version} ({get_release_channel(environ=environ)})"


__all__ = [
    "RELEASE_CHANNEL_ENV",
    "VALID_RELEASE_CHANNELS",
    "get_release_channel",
    "normalize_release_channel",
    "release_channel",
    "version",
    "version_with_channel",
]
