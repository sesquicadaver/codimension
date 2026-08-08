# -*- coding: utf-8 -*-
#
# codimension - bridge from headless CFG into Flow UI (R140.b)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Thin adapter: Flow UI canvas consumes ``core.cfg`` (R140.b).

The control-flow fragment tree remains the **layout payload** (cells/scopes).
:class:`~core.cfg.CfgGraph` is the single navigable structural model attached
to the canvas at layout time — not a second layout tree.
"""

from __future__ import annotations

from typing import Any, Optional

from core.cfg import CfgEdgeKind, CfgGraph, from_control_flow
from core.cfg_frames import nodes_covering_line


def bind_cfg_graph(canvas: Any, cflow: Any) -> CfgGraph:
    """Build a :class:`CfgGraph` from ``cflow`` and attach it to ``canvas``.

    Sets ``canvas.cfg_graph``. Layout continues to use ``cflow`` for cell
    construction; navigation and structural consumers read ``cfg_graph``.
    """
    graph = from_control_flow(cflow)
    canvas.cfg_graph = graph
    return graph


def get_bound_cfg(canvas: Any) -> Optional[CfgGraph]:
    """Return ``canvas.cfg_graph`` if present, else ``None``."""
    return getattr(canvas, "cfg_graph", None)


def require_bound_cfg(canvas: Any) -> CfgGraph:
    """Return the bound graph or raise if layout has not bound one."""
    graph = get_bound_cfg(canvas)
    if graph is None:
        raise RuntimeError("canvas has no cfg_graph; call layoutModule first")
    return graph


def module_entry_successor(graph: CfgGraph) -> Optional[str]:
    """Return the first real node after ENTRY, if any."""
    if not graph.entry_id:
        return None
    succ = graph.successors(graph.entry_id, kind=CfgEdgeKind.NEXT)
    return succ[0] if succ else None


def nodes_for_line(graph: CfgGraph, line: int):
    """Return non-synthetic nodes whose line range covers ``line``."""
    return nodes_covering_line(graph, line)
