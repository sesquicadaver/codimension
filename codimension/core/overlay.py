# -*- coding: utf-8 -*-
#
# codimension - OverlayLayer contract (R135)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""OverlayLayer protocol and registry (R135).

Qt-free attach points for flow/editor overlays. Concrete visual layers come
later (R160+); this ship registers empty layers and notifies them on
redraw/update hooks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class OverlayContext:
    """Context passed to overlay layers on host notify."""

    reason: str  # "redraw" | "update" | …
    path: Optional[str] = None
    surface: Optional[str] = None  # "flow" | "editor" | …


@runtime_checkable
class OverlayLayer(Protocol):
    """Pluggable overlay notified when a surface redraws or updates."""

    @property
    def layer_id(self) -> str:
        """Stable registry key."""

    def on_update(self, context: OverlayContext) -> None:
        """Handle a host redraw/update notification."""


def assert_overlay_layer(obj: object) -> OverlayLayer:
    """Raise ``TypeError`` if ``obj`` does not satisfy ``OverlayLayer``."""
    if not isinstance(obj, OverlayLayer):
        raise TypeError(f"object is not an OverlayLayer: {type(obj)!r}")
    return obj  # type: ignore[return-value]


class EmptyOverlayLayer:
    """No-op overlay used to prove registration / notify wiring."""

    layer_id = "empty"

    def on_update(self, context: OverlayContext) -> None:
        """Ignore the notification (intentionally empty)."""
        return None


class OverlayRegistry:
    """Named registry of OverlayLayer instances."""

    def __init__(self) -> None:
        self._layers: dict[str, OverlayLayer] = {}

    def register(self, layer: OverlayLayer) -> None:
        """Register ``layer`` under ``layer.layer_id`` (replace ok)."""
        assert_overlay_layer(layer)
        self._layers[layer.layer_id] = layer

    def unregister(self, layer_id: str) -> None:
        """Remove a layer if present."""
        self._layers.pop(layer_id, None)

    def get(self, layer_id: str) -> OverlayLayer:
        """Return a registered layer or raise ``KeyError``."""
        return self._layers[layer_id]

    def has(self, layer_id: str) -> bool:
        """Return True when ``layer_id`` is registered."""
        return layer_id in self._layers

    def layer_ids(self) -> tuple[str, ...]:
        """Return registered layer ids in insertion order."""
        return tuple(self._layers)

    def list_layers(self) -> tuple[OverlayLayer, ...]:
        """Return registered layers in insertion order."""
        return tuple(self._layers.values())

    def notify(self, context: OverlayContext) -> None:
        """Invoke ``on_update`` on every registered layer."""
        for layer in list(self._layers.values()):
            layer.on_update(context)


__all__ = [
    "EmptyOverlayLayer",
    "OverlayContext",
    "OverlayLayer",
    "OverlayRegistry",
    "assert_overlay_layer",
]
