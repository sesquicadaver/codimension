# -*- coding: utf-8 -*-
#
# codimension - graphics python two-way code editor and analyzer
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Control-flow parse result cache (R113).

Mirrors ``BriefModuleInfoCache``: path → (mtime, control-flow object).
"""

from __future__ import annotations

from os.path import exists, getmtime, realpath
from typing import Any


def _parse_control_flow_from_file(path: str) -> Any:
    """Parse via ``core.flow`` so shims / C extensions stay consistent."""
    from core.flow import parse_control_flow_from_file

    return parse_control_flow_from_file(path)


class ControlFlowInfoCache:
    """Provides a control-flow parse cache keyed by absolute path."""

    def __init__(self) -> None:
        # abs file path → (modification time, control flow)
        self.__cache: dict[str, tuple[float, Any]] = {}

    def get(self, path: str) -> Any:
        """Provide the required control-flow object, refreshing on mtime."""
        path = realpath(path)
        try:
            entry = self.__cache[path]
            if not exists(path):
                del self.__cache[path]
                raise Exception("Cannot open " + path)

            last_mod_time = getmtime(path)
            if last_mod_time <= entry[0]:
                return entry[1]

            info = _parse_control_flow_from_file(path)
            self.__cache[path] = (last_mod_time, info)
            return info
        except KeyError:
            if not exists(path):
                raise Exception("Cannot open " + path)

            info = _parse_control_flow_from_file(path)
            self.__cache[path] = (getmtime(path), info)
            return info

    def remove(self, path: str) -> None:
        """Remove one file from the map."""
        path = realpath(path)
        self.__cache.pop(path, None)

    def clear(self) -> None:
        """Clear the cache."""
        self.__cache = {}

    def __contains__(self, path: str) -> bool:
        """True when ``path`` has a cached entry (no mtime check)."""
        return realpath(path) in self.__cache

    def size(self) -> int:
        """Number of cached paths."""
        return len(self.__cache)
