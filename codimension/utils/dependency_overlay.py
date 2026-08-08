# -*- coding: utf-8 -*-
#
# codimension - dependency overlay edge heat (R161)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""DependencyGraph edge-heat overlay via OverlayLayer (R161).

Qt-free heat model from R133 graphs; R135 layer notifies UI sinks.
Normalized heat is also available for painting deps connectors.
"""

from __future__ import annotations

import logging
import os
import weakref
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from core.overlay import OverlayContext
from utils.dependency_graph import (
    DependencyEdge,
    DependencyGraph,
    build_dependency_graph,
    build_dependency_graph_from_sources,
    module_name_for_path,
)
from utils.overlay_host import OverlayHost, flow_overlay_host

_LOG = logging.getLogger("codimension.dependency_overlay")

DEPENDENCY_LAYER_ID = "dependency"

# Cap project-wide scans so overlay refresh stays interactive.
_MAX_PROJECT_FILES = 250


@dataclass(frozen=True, slots=True)
class EdgeHeat:
    """Heat for one DependencyGraph edge."""

    source: str
    target: str
    raw: int
    normalized: float
    labels: tuple[str, ...]

    @property
    def key(self) -> tuple[str, str]:
        """Stable ``(source, target)`` key."""
        return self.source, self.target


@dataclass(frozen=True, slots=True)
class DepsHeatBadgeInfo:
    """Compact badges summarizing edge heat for the flow nav bar."""

    edge_count: int
    edges_badge: str
    hot_badge: str
    tooltip: str
    heats: tuple[EdgeHeat, ...]
    focus_module: Optional[str]
    focus_max_heat: float


def edge_raw_heat(edge: DependencyEdge) -> int:
    """Raw heat: imported-name cardinality (at least 1 when the edge exists)."""
    return max(1, len(edge.labels))


def compute_edge_heats(graph: DependencyGraph) -> tuple[EdgeHeat, ...]:
    """Return per-edge heat normalized to the graph's max raw heat."""
    if not graph.edges:
        return ()
    raws = [edge_raw_heat(e) for e in graph.edges]
    max_raw = max(raws) or 1
    return tuple(
        EdgeHeat(
            source=e.source,
            target=e.target,
            raw=raw,
            normalized=raw / max_raw,
            labels=e.labels,
        )
        for e, raw in zip(graph.edges, raws, strict=True)
    )


def heats_from_module(heats: Sequence[EdgeHeat], module_id: str) -> tuple[EdgeHeat, ...]:
    """Outgoing heats for ``module_id``."""
    return tuple(h for h in heats if h.source == module_id)


def max_outgoing_heat(heats: Sequence[EdgeHeat], module_id: str) -> float:
    """Max normalized outgoing heat for ``module_id`` (0.0 when none)."""
    outs = heats_from_module(heats, module_id)
    if not outs:
        return 0.0
    return max(h.normalized for h in outs)


def heat_to_rgb(normalized: float) -> tuple[int, int, int]:
    """Map ``0..1`` heat to cool-blue → hot-red RGB (no Qt)."""
    t = 0.0 if normalized < 0 else 1.0 if normalized > 1 else float(normalized)
    # blue (80,140,220) → red (220,60,40)
    r = int(80 + (220 - 80) * t)
    g = int(140 + (60 - 140) * t)
    b = int(220 + (40 - 220) * t)
    return r, g, b


def summarize_deps_heat(
    graph: DependencyGraph,
    *,
    focus_module: Optional[str] = None,
    top_n: int = 5,
) -> DepsHeatBadgeInfo:
    """Build nav-bar badges and tooltip from a DependencyGraph."""
    heats = compute_edge_heats(graph)
    edge_count = len(heats)
    edges_badge = f"deps:{edge_count}"
    hot_badge = ""
    focus_max = 0.0
    if heats:
        hottest = max(heats, key=lambda h: (h.raw, h.normalized, h.source, h.target))
        hot_badge = f"hot:{hottest.source}→{hottest.target}"
    if focus_module:
        focus_max = max_outgoing_heat(heats, focus_module)
        focus_outs = heats_from_module(heats, focus_module)
        if focus_outs:
            local_hot = max(focus_outs, key=lambda h: (h.raw, h.normalized, h.target))
            hot_badge = f"hot:{local_hot.source}→{local_hot.target}"

    tip_lines = [f"Dependency edges: {edge_count}"]
    if focus_module:
        tip_lines.append(f"Focus module: {focus_module} (max heat {focus_max:.2f})")
    ranked = sorted(heats, key=lambda h: (-h.raw, -h.normalized, h.source, h.target))[:top_n]
    if ranked:
        tip_lines.append("Hottest edges:")
        for heat in ranked:
            labels = ",".join(heat.labels) if heat.labels else "-"
            tip_lines.append(f"  {heat.source} → {heat.target}  raw={heat.raw}  n={heat.normalized:.2f}  [{labels}]")
    return DepsHeatBadgeInfo(
        edge_count=edge_count,
        edges_badge=edges_badge,
        hot_badge=hot_badge,
        tooltip="\n".join(tip_lines),
        heats=heats,
        focus_module=focus_module,
        focus_max_heat=focus_max,
    )


def empty_deps_heat_badge() -> DepsHeatBadgeInfo:
    """Badge payload when no graph is available."""
    return DepsHeatBadgeInfo(
        edge_count=0,
        edges_badge="deps:0",
        hot_badge="",
        tooltip="No dependency edges",
        heats=(),
        focus_module=None,
        focus_max_heat=0.0,
    )


def build_graph_for_project(project, *, focus_path: Optional[str] = None) -> tuple[DependencyGraph, Optional[str]]:
    """Build a DependencyGraph from project files (capped) and resolve focus module."""
    loaded = project is not None and getattr(project, "isLoaded", lambda: False)()
    if not loaded:
        if focus_path and os.path.isfile(focus_path):
            try:
                with open(focus_path, encoding="utf-8", errors="replace") as handle:
                    source = handle.read()
            except OSError:
                return DependencyGraph(), None
            focus_root = os.path.dirname(os.path.abspath(focus_path))
            graph = build_dependency_graph_from_sources([(focus_path, source)], root=focus_root)
            return graph, module_name_for_path(focus_path, focus_root)
        return DependencyGraph(), None

    project_root: Optional[str] = None
    if hasattr(project, "getProjectDir"):
        raw_root = project.getProjectDir()
        if raw_root:
            project_root = str(raw_root)
    files: list[str] = []
    try:
        files_list = getattr(project, "filesList", None) or []
        files = [p for p in files_list if isinstance(p, str) and p.endswith(".py")]
    except Exception:
        _LOG.debug("dependency overlay: filesList unavailable", exc_info=True)
    if focus_path and os.path.isfile(focus_path) and focus_path not in files:
        files.insert(0, focus_path)
    files = files[:_MAX_PROJECT_FILES]
    if not files:
        return DependencyGraph(), None
    graph = build_dependency_graph(files, root=project_root)
    focus_mod = module_name_for_path(focus_path, project_root) if focus_path else None
    return graph, focus_mod


class DependencyOverlayLayer:
    """R135 overlay that refreshes DependencyGraph edge-heat badges."""

    layer_id = DEPENDENCY_LAYER_ID

    def __init__(self) -> None:
        self.last_badge: Optional[DepsHeatBadgeInfo] = None
        self.last_heats: tuple[EdgeHeat, ...] = ()
        self._weak_sinks: list[weakref.WeakMethod] = []
        self._strong_sinks: list[Callable[[DepsHeatBadgeInfo], None]] = []
        self._cache_key: Optional[tuple] = None
        self._cached_graph: Optional[DependencyGraph] = None

    def add_sink(self, callback: Callable[[DepsHeatBadgeInfo], None]) -> None:
        """Register a UI callback; bound methods are held weakly."""
        try:
            self._weak_sinks.append(weakref.WeakMethod(callback))  # type: ignore[arg-type]
        except TypeError:
            self._strong_sinks.append(callback)

    def on_update(self, context: OverlayContext) -> None:
        """Refresh heats using the notified file path as focus when present."""
        self.refresh(focus_path=context.path)

    def refresh(self, project=None, *, focus_path: Optional[str] = None) -> DepsHeatBadgeInfo:
        """Recompute edge heats and notify sinks."""
        if project is None:
            try:
                from utils.globals import GlobalData

                project = GlobalData().project
            except Exception:
                _LOG.debug("dependency overlay: GlobalData unavailable", exc_info=True)
                project = None
        try:
            graph, focus_mod = self._graph_for(project, focus_path=focus_path)
            badge = summarize_deps_heat(graph, focus_module=focus_mod)
        except Exception:
            _LOG.debug("dependency overlay: refresh failed", exc_info=True)
            badge = empty_deps_heat_badge()
        self.last_badge = badge
        self.last_heats = badge.heats
        self._notify(badge)
        return badge

    def _graph_for(self, project, *, focus_path: Optional[str]) -> tuple[DependencyGraph, Optional[str]]:
        """Return a (possibly cached) graph for the project / focus file."""
        project_id = None
        files_sig = 0
        if project is not None and getattr(project, "isLoaded", lambda: False)():
            project_id = getattr(project, "getProjectUUID", lambda: None)() or id(project)
            try:
                files_sig = len(getattr(project, "filesList", []) or [])
            except Exception:
                files_sig = 0
        key = (project_id, files_sig, focus_path)
        if key == self._cache_key and self._cached_graph is not None:
            focus_mod = None
            if focus_path and project is not None and getattr(project, "isLoaded", lambda: False)():
                root = project.getProjectDir()
                focus_mod = module_name_for_path(focus_path, root)
            elif focus_path:
                focus_mod = module_name_for_path(focus_path, os.path.dirname(os.path.abspath(focus_path)))
            return self._cached_graph, focus_mod
        graph, focus_mod = build_graph_for_project(project, focus_path=focus_path)
        self._cache_key = key
        self._cached_graph = graph
        return graph, focus_mod

    def _notify(self, badge: DepsHeatBadgeInfo) -> None:
        alive: list[weakref.WeakMethod] = []
        for ref in self._weak_sinks:
            cb = ref()
            if cb is None:
                continue
            alive.append(ref)
            try:
                cb(badge)
            except Exception:
                _LOG.debug("dependency overlay sink failed", exc_info=True)
        self._weak_sinks = alive
        for cb in list(self._strong_sinks):
            try:
                cb(badge)
            except Exception:
                _LOG.debug("dependency overlay sink failed", exc_info=True)


def ensure_dependency_overlay(host: Optional[OverlayHost] = None) -> DependencyOverlayLayer:
    """Register the dependency heat overlay on the flow host if missing."""
    target = host if host is not None else flow_overlay_host()
    if target.registry.has(DEPENDENCY_LAYER_ID):
        layer = target.registry.get(DEPENDENCY_LAYER_ID)
        assert isinstance(layer, DependencyOverlayLayer)
        return layer
    layer = DependencyOverlayLayer()
    target.register(layer)
    return layer


__all__ = [
    "DEPENDENCY_LAYER_ID",
    "DepsHeatBadgeInfo",
    "DependencyOverlayLayer",
    "EdgeHeat",
    "build_graph_for_project",
    "compute_edge_heats",
    "edge_raw_heat",
    "empty_deps_heat_badge",
    "ensure_dependency_overlay",
    "heat_to_rgb",
    "heats_from_module",
    "max_outgoing_heat",
    "summarize_deps_heat",
]
