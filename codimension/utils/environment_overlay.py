# -*- coding: utf-8 -*-
#
# codimension - environment overlay layer (R160)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Environment source / path badges via OverlayLayer (R160).

Qt-free data + R135 layer. UI widgets subscribe as sinks and render
``EnvBadgeInfo`` on the flow surface.
"""

from __future__ import annotations

import logging
import os
import sys
import weakref
from dataclasses import dataclass
from typing import Callable, Optional

from core.overlay import OverlayContext
from utils.overlay_host import OverlayHost, flow_overlay_host

_LOG = logging.getLogger("codimension.environment_overlay")

ENVIRONMENT_LAYER_ID = "environment"

_SOURCE_BADGES = {
    "configured": "env:project",
    "session": "env:session",
    "auto": "env:auto",
    "ide": "env:IDE",
    "invalid": "env:broken",
}


@dataclass(frozen=True, slots=True)
class EnvBadgeInfo:
    """Compact source + path badges for the flow UI overlay."""

    source_kind: str
    source_badge: str
    path_badge: str
    tooltip: str


def truncate_path_badge(path: str, *, max_chars: int = 40) -> str:
    """Return a short path badge (prefer basename when truncated)."""
    text = (path or "").strip()
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    base = os.path.basename(text.rstrip(os.sep))
    if not base:
        return text[: max_chars - 1] + "…"
    if len(base) >= max_chars:
        return base[: max_chars - 1] + "…"
    # Keep a little parent context when space allows.
    prefix_budget = max_chars - len(base) - 1
    if prefix_budget < 2:
        return "…" + base
    parent = os.path.dirname(text)
    if len(parent) <= prefix_budget:
        return parent + os.sep + base if parent else base
    return "…" + parent[-(prefix_budget - 1) :] + os.sep + base


def format_env_badge_info(
    source_kind: str,
    python_path: str,
    *,
    tooltip: Optional[str] = None,
    max_path_chars: int = 40,
) -> EnvBadgeInfo:
    """Build badge texts from a describe-style ``(kind, path)`` pair."""
    kind = (source_kind or "ide").strip() or "ide"
    source_badge = _SOURCE_BADGES.get(kind, f"env:{kind}")
    path = python_path or ""
    tip = tooltip if tooltip is not None else path
    return EnvBadgeInfo(
        source_kind=kind,
        source_badge=source_badge,
        path_badge=truncate_path_badge(path, max_chars=max_path_chars),
        tooltip=tip or "",
    )


def format_env_badge_from_project(project) -> EnvBadgeInfo:
    """Build badges from the live analysis environment for ``project``."""
    from utils.venvbootstrap import buildAnalysisEnvironment, formatAnalysisEnvStatus

    env = buildAnalysisEnvironment(project)
    _label, tip = formatAnalysisEnvStatus(project)
    return format_env_badge_info(env.source_kind, env.python_path, tooltip=tip)


class EnvironmentOverlayLayer:
    """R135 overlay that refreshes env source/path badges for flow sinks."""

    layer_id = ENVIRONMENT_LAYER_ID

    def __init__(self) -> None:
        self.last_badge: Optional[EnvBadgeInfo] = None
        self._weak_sinks: list[weakref.WeakMethod] = []
        self._strong_sinks: list[Callable[[EnvBadgeInfo], None]] = []

    def add_sink(self, callback: Callable[[EnvBadgeInfo], None]) -> None:
        """Register a UI callback; bound methods are held weakly."""
        try:
            self._weak_sinks.append(weakref.WeakMethod(callback))  # type: ignore[arg-type]
        except TypeError:
            self._strong_sinks.append(callback)

    def on_update(self, context: OverlayContext) -> None:
        """Refresh badges on flow redraw / env notify."""
        del context  # path unused; env is project-global
        self.refresh()

    def refresh(self, project=None) -> EnvBadgeInfo:
        """Recompute badges and notify sinks."""
        if project is None:
            try:
                from utils.globals import GlobalData

                project = GlobalData().project
            except Exception:
                _LOG.debug("environment overlay: GlobalData unavailable", exc_info=True)
                project = None
        if project is None:
            badge = format_env_badge_info("ide", sys.executable)
        else:
            try:
                badge = format_env_badge_from_project(project)
            except Exception:
                _LOG.debug("environment overlay: project badge failed", exc_info=True)
                badge = format_env_badge_info("ide", sys.executable)
        self.last_badge = badge
        alive: list[weakref.WeakMethod] = []
        for ref in self._weak_sinks:
            cb = ref()
            if cb is None:
                continue
            alive.append(ref)
            try:
                cb(badge)
            except Exception:
                _LOG.debug("environment overlay sink failed", exc_info=True)
        self._weak_sinks = alive
        for cb in list(self._strong_sinks):
            try:
                cb(badge)
            except Exception:
                _LOG.debug("environment overlay sink failed", exc_info=True)
        return badge


def ensure_environment_overlay(host: Optional[OverlayHost] = None) -> EnvironmentOverlayLayer:
    """Register the environment overlay on the flow host if missing."""
    target = host if host is not None else flow_overlay_host()
    if target.registry.has(ENVIRONMENT_LAYER_ID):
        layer = target.registry.get(ENVIRONMENT_LAYER_ID)
        assert isinstance(layer, EnvironmentOverlayLayer)
        return layer
    layer = EnvironmentOverlayLayer()
    target.register(layer)
    return layer


__all__ = [
    "ENVIRONMENT_LAYER_ID",
    "EnvBadgeInfo",
    "EnvironmentOverlayLayer",
    "ensure_environment_overlay",
    "format_env_badge_from_project",
    "format_env_badge_info",
    "truncate_path_badge",
]
