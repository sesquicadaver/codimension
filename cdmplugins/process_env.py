# -*- coding: utf-8 -*-
#
# codimension - shared QProcess environment for tool drivers
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Build a QProcessEnvironment that inherits the system environment (T030)."""

from __future__ import annotations

from typing import Any, Callable, Mapping


def build_tool_process_environment(
    encoding: str = "utf-8",
    overrides: Mapping[str, str] | None = None,
    *,
    env_factory: Callable[[], Any] | None = None,
) -> Any:
    """Return a process environment based on the parent process.

    Uses ``QProcessEnvironment.systemEnvironment()`` unless ``env_factory`` is
    provided (tests). Always sets ``PYTHONIOENCODING``.
    """
    if env_factory is not None:
        env = env_factory()
    else:
        from ui.qt import QProcessEnvironment

        env = QProcessEnvironment.systemEnvironment()
    env.insert("PYTHONIOENCODING", encoding or "utf-8")
    if overrides:
        for key, value in overrides.items():
            env.insert(str(key), str(value))
    return env
