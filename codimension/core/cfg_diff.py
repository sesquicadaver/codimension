# -*- coding: utf-8 -*-
#
# codimension - CFG graph diff (R142)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Structural diff between two headless CFG graphs (R142).

Node ids from :mod:`core.cfg` are allocation-order and unstable across
parses, so matching uses a content key ``(kind, label, begin_line,
end_line, frag_kind)``. Edges are matched by the stable keys of their
endpoints plus edge kind/label.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.cfg import CfgEdge, CfgGraph, CfgNode, build_cfg_graph

NodeKey = tuple[str, str, int, int, Optional[int]]
EdgeKey = tuple[NodeKey, NodeKey, str, str]


def node_key(node: CfgNode) -> NodeKey:
    """Stable content key for a CFG node (independent of allocation id)."""
    return (
        str(node.kind.value),
        str(node.label or ""),
        int(node.begin_line),
        int(node.end_line),
        int(node.frag_kind) if node.frag_kind is not None else None,
    )


def edge_key(edge: CfgEdge, nodes: dict[str, CfgNode]) -> Optional[EdgeKey]:
    """Stable content key for an edge, or ``None`` if endpoints are missing."""
    src = nodes.get(edge.src)
    dst = nodes.get(edge.dst)
    if src is None or dst is None:
        return None
    return (node_key(src), node_key(dst), str(edge.kind.value), str(edge.label or ""))


@dataclass(frozen=True)
class CfgNodeChange:
    """Same content key is not used; represents a line/label drift pair.

    Matched when ``kind`` + ``frag_kind`` + ``label`` agree but line span
    differs (typical edit that shifts a fragment).
    """

    before: CfgNode
    after: CfgNode


@dataclass(frozen=True)
class CfgGraphDiff:
    """Result of comparing two CFG graphs."""

    added_nodes: tuple[CfgNode, ...]
    removed_nodes: tuple[CfgNode, ...]
    changed_nodes: tuple[CfgNodeChange, ...]
    added_edges: tuple[CfgEdge, ...]
    removed_edges: tuple[CfgEdge, ...]

    @property
    def empty(self) -> bool:
        """True when the graphs are structurally identical under content keys."""
        return not (
            self.added_nodes or self.removed_nodes or self.changed_nodes or self.added_edges or self.removed_edges
        )

    def summary(self) -> dict[str, int]:
        """Compact counts for logging / tests."""
        return {
            "added_nodes": len(self.added_nodes),
            "removed_nodes": len(self.removed_nodes),
            "changed_nodes": len(self.changed_nodes),
            "added_edges": len(self.added_edges),
            "removed_edges": len(self.removed_edges),
        }


def _identity_key(node: CfgNode) -> tuple[str, str, Optional[int]]:
    """Soft identity for detecting relocated fragments (ignore line span)."""
    return (str(node.kind.value), str(node.label or ""), int(node.frag_kind) if node.frag_kind is not None else None)


def diff_cfg_graphs(before: CfgGraph, after: CfgGraph) -> CfgGraphDiff:
    """Diff ``before`` against ``after`` using stable content keys."""
    before_by_key = {node_key(n): n for n in before.nodes.values()}
    after_by_key = {node_key(n): n for n in after.nodes.values()}

    shared_keys = set(before_by_key) & set(after_by_key)
    only_before = set(before_by_key) - shared_keys
    only_after = set(after_by_key) - shared_keys

    # Pair removed/added that share soft identity → changed (moved/edited span).
    before_soft: dict[tuple[str, str, Optional[int]], list[CfgNode]] = {}
    for key in only_before:
        node = before_by_key[key]
        before_soft.setdefault(_identity_key(node), []).append(node)
    after_soft: dict[tuple[str, str, Optional[int]], list[CfgNode]] = {}
    for key in only_after:
        node = after_by_key[key]
        after_soft.setdefault(_identity_key(node), []).append(node)

    changed: list[CfgNodeChange] = []
    consumed_before: set[str] = set()
    consumed_after: set[str] = set()
    for soft, befores in before_soft.items():
        afters = after_soft.get(soft) or []
        pairs = min(len(befores), len(afters))
        for i in range(pairs):
            changed.append(CfgNodeChange(before=befores[i], after=afters[i]))
            consumed_before.add(befores[i].id)
            consumed_after.add(afters[i].id)

    removed = tuple(before_by_key[k] for k in sorted(only_before) if before_by_key[k].id not in consumed_before)
    added = tuple(after_by_key[k] for k in sorted(only_after) if after_by_key[k].id not in consumed_after)

    before_edges = {ek: e for e in before.edges if (ek := edge_key(e, before.nodes)) is not None}
    after_edges = {ek: e for e in after.edges if (ek := edge_key(e, after.nodes)) is not None}
    added_edges = tuple(after_edges[k] for k in sorted(set(after_edges) - set(before_edges)))
    removed_edges = tuple(before_edges[k] for k in sorted(set(before_edges) - set(after_edges)))

    changed_sorted = tuple(sorted(changed, key=lambda c: (node_key(c.before), node_key(c.after))))
    return CfgGraphDiff(
        added_nodes=added,
        removed_nodes=removed,
        changed_nodes=changed_sorted,
        added_edges=added_edges,
        removed_edges=removed_edges,
    )


def diff_cfg_sources(before_source: str, after_source: str) -> CfgGraphDiff:
    """Parse two source strings and return their CFG diff."""
    return diff_cfg_graphs(build_cfg_graph(before_source), build_cfg_graph(after_source))


__all__ = [
    "CfgGraphDiff",
    "CfgNodeChange",
    "diff_cfg_graphs",
    "diff_cfg_sources",
    "edge_key",
    "node_key",
]
