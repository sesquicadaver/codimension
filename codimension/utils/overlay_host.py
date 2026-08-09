# -*- coding: utf-8 -*-
#
# codimension - flow/editor overlay attach points (R135)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Overlay attach hosts for flow and editor surfaces (R135).

Surfaces call ``notify_*`` after redraw/update; layers register on the
corresponding host registry. Default empty layer is optional.
"""

from __future__ import annotations

from typing import Optional

from core.overlay import EmptyOverlayLayer, OverlayContext, OverlayRegistry


class OverlayHost:
    """Attach point wrapping an OverlayRegistry for one UI surface."""

    def __init__(self, surface: str) -> None:
        self.surface = surface
        self.registry = OverlayRegistry()

    def register(self, layer: object) -> None:
        """Register a layer on this host."""
        self.registry.register(layer)  # type: ignore[arg-type]

    def notify(self, reason: str, *, path: Optional[str] = None) -> None:
        """Notify all layers with a surface-tagged context."""
        self.registry.notify(OverlayContext(reason=reason, path=path, surface=self.surface))


_FLOW_HOST = OverlayHost("flow")
_EDITOR_HOST = OverlayHost("editor")


def flow_overlay_host() -> OverlayHost:
    """Return the process-wide flow overlay attach point."""
    return _FLOW_HOST


def editor_overlay_host() -> OverlayHost:
    """Return the process-wide editor overlay attach point."""
    return _EDITOR_HOST


def notify_flow_overlays(reason: str, *, path: Optional[str] = None) -> None:
    """Notify flow-surface overlay layers (no-op in R175 safe mode)."""
    from core.safe_mode import is_safe_mode_enabled

    if is_safe_mode_enabled():
        return
    _FLOW_HOST.notify(reason, path=path)


def notify_editor_overlays(reason: str, *, path: Optional[str] = None) -> None:
    """Notify editor-surface overlay layers (no-op in R175 safe mode)."""
    from core.safe_mode import is_safe_mode_enabled

    if is_safe_mode_enabled():
        return
    _EDITOR_HOST.notify(reason, path=path)


def ensure_empty_overlay(host: OverlayHost) -> EmptyOverlayLayer:
    """Register the shared empty overlay on ``host`` if missing."""
    if not host.registry.has("empty"):
        layer = EmptyOverlayLayer()
        host.register(layer)
        return layer
    return host.registry.get("empty")  # type: ignore[return-value]


def ensure_environment_overlay(host: Optional[OverlayHost] = None):
    """Register the R160 environment badge overlay on the flow host if missing."""
    from utils.environment_overlay import ensure_environment_overlay as _ensure

    return _ensure(host)


def ensure_dependency_overlay(host: Optional[OverlayHost] = None):
    """Register the R161 dependency edge-heat overlay on the flow host if missing."""
    from utils.dependency_overlay import ensure_dependency_overlay as _ensure

    return _ensure(host)


def ensure_deployment_overlay(host: Optional[OverlayHost] = None):
    """Register the R162 deployment hint overlay on the flow host if missing."""
    from utils.deployment_overlay import ensure_deployment_overlay as _ensure

    return _ensure(host)


__all__ = [
    "OverlayHost",
    "editor_overlay_host",
    "ensure_dependency_overlay",
    "ensure_deployment_overlay",
    "ensure_empty_overlay",
    "ensure_environment_overlay",
    "flow_overlay_host",
    "notify_editor_overlays",
    "notify_flow_overlays",
]
