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

"""Headless DependencyGraph from Python imports (R133 / R207).

Builds a Qt-free graph of modules and import edges using ``brief_ast``.
Resolution is limited to the provided file set (project-local modules);
everything else becomes an ``external`` node. Full ``resolveImports`` /
GlobalData path stays in the UI diagram code.

R207: edges carry :class:`~core.dependency_edges.DependencyEdgeKind`
(default ``PYTHON_IMPORT``). Polyglot FFI / cross-nav live in
``core.dependency_edges`` / ``core.cross_language_nav``.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Optional

from core.dependency_edges import DependencyEdgeKind
from parsers.brief_ast import getBriefModuleInfoFromFile, getBriefModuleInfoFromMemory


@dataclass(frozen=True, slots=True)
class DependencyNode:
    """A module / package node in the dependency graph."""

    id: str
    kind: str  # "file" | "external" | "package"
    path: Optional[str] = None
    label: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable node dict."""
        data: dict[str, Any] = {"id": self.id, "kind": self.kind}
        if self.path is not None:
            data["path"] = self.path
        if self.label is not None:
            data["label"] = self.label
        return data


@dataclass(frozen=True, slots=True)
class DependencyEdge:
    """Directed import edge ``source -> target``."""

    source: str
    target: str
    labels: tuple[str, ...] = ()
    line: Optional[int] = None
    kind: DependencyEdgeKind = DependencyEdgeKind.PYTHON_IMPORT

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable edge dict."""
        data: dict[str, Any] = {
            "source": self.source,
            "target": self.target,
            "labels": list(self.labels),
            "kind": self.kind.value,
        }
        if self.line is not None:
            data["line"] = self.line
        return data


@dataclass
class DependencyGraph:
    """In-memory import dependency graph with optional JSON / DOT export."""

    nodes: dict[str, DependencyNode] = field(default_factory=dict)
    edges: list[DependencyEdge] = field(default_factory=list)

    def add_node(self, node: DependencyNode) -> DependencyNode:
        """Insert or return an existing node with the same id."""
        existing = self.nodes.get(node.id)
        if existing is not None:
            return existing
        self.nodes[node.id] = node
        return node

    def add_edge(self, edge: DependencyEdge) -> None:
        """Append an edge, merging labels when source/target/kind already exist."""
        for idx, current in enumerate(self.edges):
            if current.source == edge.source and current.target == edge.target and current.kind is edge.kind:
                merged = tuple(dict.fromkeys(current.labels + edge.labels))
                line = current.line if current.line is not None else edge.line
                self.edges[idx] = DependencyEdge(
                    edge.source,
                    edge.target,
                    merged,
                    line,
                    kind=edge.kind,
                )
                return
        self.edges.append(edge)

    def node_ids(self) -> tuple[str, ...]:
        """Return all node ids."""
        return tuple(self.nodes)

    def successors(self, node_id: str) -> tuple[str, ...]:
        """Return targets of edges leaving ``node_id``."""
        return tuple(e.target for e in self.edges if e.source == node_id)

    def predecessors(self, node_id: str) -> tuple[str, ...]:
        """Return sources of edges entering ``node_id``."""
        return tuple(e.source for e in self.edges if e.target == node_id)

    def to_json_obj(self) -> dict[str, Any]:
        """Return a JSON-serializable object."""
        return {
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges],
        }

    def to_json(self, *, indent: Optional[int] = 2) -> str:
        """Serialize the graph as a JSON string."""
        return json.dumps(self.to_json_obj(), indent=indent, sort_keys=True)

    def to_dot(self) -> str:
        """Serialize as a minimal Graphviz digraph (no layout hints)."""
        lines = ["digraph DependencyGraph {"]
        for node in self.nodes.values():
            label = node.label or node.id
            lines.append(f'  "{node.id}" [label="{_dot_escape(label)}", kind="{node.kind}"];')
        for edge in self.edges:
            if edge.labels:
                lab = ",".join(edge.labels)
                lines.append(f'  "{edge.source}" -> "{edge.target}" [label="{_dot_escape(lab)}"];')
            else:
                lines.append(f'  "{edge.source}" -> "{edge.target}";')
        lines.append("}")
        return "\n".join(lines)


def _dot_escape(value: str) -> str:
    """Escape a label for DOT double quotes."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def module_name_for_path(path: str, root: Optional[str] = None) -> str:
    """Map a ``.py`` path to a dotted module name relative to ``root``."""
    abs_path = os.path.abspath(path)
    base = os.path.abspath(root) if root else os.path.dirname(abs_path)
    try:
        rel = os.path.relpath(abs_path, base)
    except ValueError:
        rel = os.path.basename(abs_path)
    if rel.endswith(".py"):
        rel = rel[:-3]
    if rel.endswith(os.sep + "__init__") or rel == "__init__":
        rel = rel[: -len("__init__")].rstrip(os.sep)
    return rel.replace(os.sep, ".").replace("/", ".")


def build_dependency_graph(
    paths: Sequence[str] | Iterable[str],
    *,
    root: Optional[str] = None,
    on_file: Optional[Callable[[str], None]] = None,
) -> DependencyGraph:
    """Build a dependency graph for the given Python file paths.

    ``on_file(path)`` is invoked before each file is parsed (async-friendly).
    """
    path_list = [os.path.abspath(p) for p in paths]
    graph_root = (
        os.path.abspath(root)
        if root
        else (os.path.commonpath(path_list) if len(path_list) > 1 else os.path.dirname(path_list[0]))
    )
    graph = DependencyGraph()
    file_by_module: dict[str, str] = {}

    for path in path_list:
        mod = module_name_for_path(path, graph_root)
        file_by_module[mod] = path
        graph.add_node(DependencyNode(id=mod, kind="file", path=path, label=mod))

    for path in path_list:
        if on_file is not None:
            on_file(path)
        source_mod = module_name_for_path(path, graph_root)
        try:
            info = getBriefModuleInfoFromFile(path)
        except OSError:
            continue
        if not info.isOK:
            continue
        _add_imports(graph, source_mod, info.imports, file_by_module)
    return graph


def build_dependency_graph_from_sources(
    items: Sequence[tuple[str, str]],
    *,
    root: Optional[str] = None,
) -> DependencyGraph:
    """Build a graph from ``(path, source)`` pairs (tests / in-memory projects)."""
    path_list = [os.path.abspath(p) for p, _ in items]
    graph_root = (
        os.path.abspath(root)
        if root
        else (os.path.commonpath(path_list) if len(path_list) > 1 else os.path.dirname(path_list[0] or "."))
    )
    if graph_root in ("", "."):
        graph_root = os.getcwd()
    graph = DependencyGraph()
    file_by_module: dict[str, str] = {}
    for path, _source in items:
        abs_path = os.path.abspath(path)
        mod = module_name_for_path(abs_path, graph_root)
        file_by_module[mod] = abs_path
        graph.add_node(DependencyNode(id=mod, kind="file", path=abs_path, label=mod))

    for path, source in items:
        abs_path = os.path.abspath(path)
        source_mod = module_name_for_path(abs_path, graph_root)
        info = getBriefModuleInfoFromMemory(source, abs_path)
        if not info.isOK:
            continue
        _add_imports(graph, source_mod, info.imports, file_by_module)
    return graph


def _add_imports(
    graph: DependencyGraph, source_mod: str, imports: Sequence[Any], file_by_module: dict[str, str]
) -> None:
    """Add edges for brief_ast import objects from ``source_mod``."""
    for imp in imports:
        target_name = str(imp.name)
        labels = tuple(str(w.name) for w in getattr(imp, "what", []) or [])
        line = getattr(imp, "line", None)
        try:
            line_i = int(line) if line is not None else None
        except (TypeError, ValueError):
            line_i = None

        if target_name in file_by_module:
            target_id = target_name
            kind = "file"
            path = file_by_module[target_name]
        else:
            # Prefer a longer local prefix match (pkg.sub -> pkg.sub when present).
            target_id = target_name
            kind = "external"
            path = None
            for mod_name, mod_path in file_by_module.items():
                if target_name == mod_name or target_name.startswith(mod_name + "."):
                    target_id = mod_name
                    kind = "file"
                    path = mod_path
                    break

        graph.add_node(DependencyNode(id=target_id, kind=kind, path=path, label=target_id))
        graph.add_edge(
            DependencyEdge(
                source=source_mod,
                target=target_id,
                labels=labels,
                line=line_i,
            )
        )


def to_polyglot_graph(python_graph: DependencyGraph) -> Any:
    """Lift a Python import :class:`DependencyGraph` into a polyglot graph (R207).

    Returns a :class:`~core.dependency_edges.PolyglotDependencyGraph`.
    """
    from core.dependency_edges import (
        PolyglotDependencyGraph,
        TypedDependencyEdge,
        TypedDependencyNode,
        ingest_python_import_edges,
    )

    poly = PolyglotDependencyGraph()
    for node in python_graph.nodes.values():
        poly.add_node(
            TypedDependencyNode(
                id=node.id,
                language_id="python",
                kind=node.kind,
                path=node.path,
                label=node.label,
            )
        )
    ingest_python_import_edges(
        poly,
        edges=((e.source, e.target, e.labels) for e in python_graph.edges),
    )
    for edge in python_graph.edges:
        if edge.kind is not DependencyEdgeKind.PYTHON_IMPORT:
            poly.add_edge(
                TypedDependencyEdge(
                    source=edge.source,
                    target=edge.target,
                    kind=edge.kind,
                    labels=edge.labels,
                )
            )
    return poly


__all__ = [
    "DependencyEdge",
    "DependencyEdgeKind",
    "DependencyGraph",
    "DependencyNode",
    "build_dependency_graph",
    "build_dependency_graph_from_sources",
    "module_name_for_path",
    "to_polyglot_graph",
]
