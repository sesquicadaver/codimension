# -*- coding: utf-8 -*-
#
# codimension - portable config home (R180)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Portable config root via ``CDM_HOME`` (R180).

When ``CDM_HOME`` is set to a non-empty path, Codimension stores
``.codimension3`` (updates cache, apply-state, feature flags) under that
directory instead of the process home. Full ``SETTINGS_DIR`` Qt singleton
override is out of scope for this thin layer.
"""

from __future__ import annotations

import os
from typing import Mapping, Optional

from utils.config import CONFIG_DIR

#: Environment variable selecting an alternate config home directory.
CDM_HOME_ENV = "CDM_HOME"


def resolve_config_home(
    environ: Optional[Mapping[str, str]] = None,
    *,
    home: Optional[str] = None,
) -> str:
    """Return the absolute config home directory.

    Precedence: explicit ``home`` → ``CDM_HOME`` → ``~``.
    """
    if home is not None:
        return os.path.realpath(os.path.expanduser(home))
    env = environ if environ is not None else os.environ
    raw = str(env.get(CDM_HOME_ENV, "") or "").strip()
    if raw:
        return os.path.realpath(os.path.expanduser(raw))
    return os.path.realpath(os.path.expanduser("~"))


def config_dir(
    environ: Optional[Mapping[str, str]] = None,
    *,
    home: Optional[str] = None,
) -> str:
    """Return ``<config-home>/.codimension3``."""
    return os.path.join(resolve_config_home(environ, home=home), CONFIG_DIR)


def updates_cache_dir(
    environ: Optional[Mapping[str, str]] = None,
    *,
    home: Optional[str] = None,
) -> str:
    """Return ``<config-home>/.codimension3/updates``."""
    return os.path.join(config_dir(environ, home=home), "updates")


__all__ = [
    "CDM_HOME_ENV",
    "config_dir",
    "resolve_config_home",
    "updates_cache_dir",
]
