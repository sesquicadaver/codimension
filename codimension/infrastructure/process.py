# -*- coding: utf-8 -*-
#
# codimension - headless process environment dicts (T082)
# Copyright (C) 2026  Codimension
#

"""Build subprocess environment mappings without Qt (headless tools)."""

from __future__ import annotations

import os
from collections.abc import Mapping


def build_tool_environ(
    encoding: str = "utf-8",
    overrides: Mapping[str, str] | None = None,
    *,
    base: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return a ``dict`` suitable for ``subprocess`` ``env=``.

    Mirrors the intent of ``cdmplugins.process_env.build_tool_process_environment``
    without requiring ``QProcessEnvironment`` / Qt.
    """
    env = dict(base if base is not None else os.environ)
    env["PYTHONIOENCODING"] = encoding or "utf-8"
    if overrides:
        for key, value in overrides.items():
            env[str(key)] = str(value)
    return env
