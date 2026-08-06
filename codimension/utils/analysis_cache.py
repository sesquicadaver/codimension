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

"""Analysis cache registry (R113).

Central place to register brief / control-flow (and future) analysis caches
and invalidate them on environment refresh, project rescan, or file change.
"""

from __future__ import annotations

from dataclasses import dataclass
from os.path import realpath
from typing import Callable, Literal, Optional, Protocol

InvalidateScope = Literal["project", "file", "env"]

VALID_INVALIDATE_SCOPES: frozenset[str] = frozenset({"project", "file", "env"})


class AnalysisCache(Protocol):
    """Minimal contract for a registered analysis cache."""

    @property
    def name(self) -> str:
        """Stable registry key (e.g. ``brief``, ``flow``)."""

    def invalidate_file(self, path: str) -> None:
        """Drop cached data for one filesystem path."""

    def invalidate_all(self) -> None:
        """Drop all entries (env / project-wide purge)."""


@dataclass(frozen=True)
class CallableAnalysisCache:
    """Adapter that wraps ``remove(path)`` / ``clear()`` style caches."""

    name: str
    _remove: Callable[[str], None]
    _clear: Callable[[], None]

    def invalidate_file(self, path: str) -> None:
        """Forward to the wrapped per-file remover."""
        self._remove(path)

    def invalidate_all(self) -> None:
        """Forward to the wrapped full clear."""
        self._clear()


class AnalysisCacheRegistry:
    """Named registry of analysis caches with scoped invalidation."""

    def __init__(self) -> None:
        self._caches: dict[str, AnalysisCache] = {}

    def register(self, cache: AnalysisCache) -> None:
        """Register or replace a cache by ``cache.name``."""
        name = (cache.name or "").strip()
        if not name:
            raise ValueError("analysis cache name must be non-empty")
        self._caches[name] = cache

    def unregister(self, name: str) -> None:
        """Remove a cache by name; no-op if missing."""
        self._caches.pop(name, None)

    def get(self, name: str) -> Optional[AnalysisCache]:
        """Return a registered cache or ``None``."""
        return self._caches.get(name)

    def names(self) -> tuple[str, ...]:
        """Registered cache names in insertion order."""
        return tuple(self._caches.keys())

    def invalidate(self, scope: InvalidateScope, *, path: Optional[str] = None) -> int:
        """Invalidate registered caches for ``scope``.

        - ``file``: requires ``path``; calls ``invalidate_file`` on each cache
        - ``env`` / ``project``: call ``invalidate_all`` on each cache

        Returns the number of caches notified.
        """
        if scope not in VALID_INVALIDATE_SCOPES:
            raise ValueError(f"unknown invalidate scope: {scope!r}")
        if scope == "file":
            if not path:
                raise ValueError("invalidate(scope='file') requires path=")
            norm = realpath(path)
            for cache in self._caches.values():
                cache.invalidate_file(norm)
            return len(self._caches)
        for cache in self._caches.values():
            cache.invalidate_all()
        return len(self._caches)

    def clear_registry(self) -> None:
        """Drop all registrations (test helper)."""
        self._caches.clear()


_registry: Optional[AnalysisCacheRegistry] = None
_brief_cache = None  # BriefModuleInfoCache | None
_flow_cache = None  # ControlFlowInfoCache | None


def get_analysis_cache_registry() -> AnalysisCacheRegistry:
    """Return the process-wide analysis cache registry."""
    global _registry
    if _registry is None:
        _registry = AnalysisCacheRegistry()
    return _registry


def ensure_default_analysis_caches() -> AnalysisCacheRegistry:
    """Register brief + flow mtime caches if not already present."""
    from .briefmodinfocache import BriefModuleInfoCache
    from .controlflowinfocache import ControlFlowInfoCache

    global _brief_cache, _flow_cache
    reg = get_analysis_cache_registry()
    if _brief_cache is None:
        _brief_cache = BriefModuleInfoCache()
    if reg.get("brief") is None:
        reg.register(
            CallableAnalysisCache(
                "brief",
                _brief_cache.remove,
                _brief_cache.clear,
            )
        )
    if _flow_cache is None:
        _flow_cache = ControlFlowInfoCache()
    if reg.get("flow") is None:
        reg.register(
            CallableAnalysisCache(
                "flow",
                _flow_cache.remove,
                _flow_cache.clear,
            )
        )
    return reg


def get_brief_module_info_cache():
    """Return the shared brief-module info cache (creates defaults)."""
    ensure_default_analysis_caches()
    return _brief_cache


def get_control_flow_info_cache():
    """Return the shared control-flow info cache (creates defaults)."""
    ensure_default_analysis_caches()
    return _flow_cache


def invalidate_analysis_caches(scope: InvalidateScope, *, path: Optional[str] = None) -> int:
    """Invalidate via the process registry (no-op when nothing registered)."""
    return get_analysis_cache_registry().invalidate(scope, path=path)


def reset_analysis_cache_registry_for_tests() -> None:
    """Drop registry and default caches so the next accessor rebuilds them."""
    global _registry, _brief_cache, _flow_cache
    if _registry is not None:
        _registry.clear_registry()
    _registry = None
    _brief_cache = None
    _flow_cache = None
