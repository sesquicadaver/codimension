# -*- coding: utf-8 -*-
#
# codimension - polyglot typed dependency edges (R207)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Typed dependency edges + polyglot graph (R207).

Generalizes the Python-only import graph with :class:`DependencyEdgeKind`
(including ``FFI_BINDING``). Cross-language hops use evidence from
:class:`~core.bindings.BindingIndex` — never name equality alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Optional

from .bindings import BindingEdge, BindingIndex, BindingPrecision, PyiStubSymbol


class DependencyEdgeKind(str, Enum):
    """Language-neutral dependency edge classification (R207)."""

    PYTHON_IMPORT = "python.import"
    RUST_USE = "rust.use"
    RUST_CRATE = "rust.crate"
    CPP_INCLUDE = "cpp.include"
    BUILD_DEPENDENCY = "build.dependency"
    LINK_DEPENDENCY = "link.dependency"
    FFI_BINDING = "ffi.binding"
    GENERATED_FROM = "generated.from"
    CALLS = "calls"


@dataclass(frozen=True, slots=True)
class TypedDependencyNode:
    """Node in a polyglot dependency graph."""

    id: str
    language_id: str
    kind: str = "symbol"  # module | symbol | stub | external
    path: Optional[str] = None
    label: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable node dict."""
        data: dict[str, Any] = {
            "id": self.id,
            "language_id": self.language_id,
            "kind": self.kind,
        }
        if self.path is not None:
            data["path"] = self.path
        if self.label is not None:
            data["label"] = self.label
        return data


@dataclass(frozen=True, slots=True)
class TypedDependencyEdge:
    """Directed typed edge ``source -> target``."""

    source: str
    target: str
    kind: DependencyEdgeKind
    labels: tuple[str, ...] = ()
    framework: str = ""
    precision: str = ""

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable edge dict."""
        data: dict[str, Any] = {
            "source": self.source,
            "target": self.target,
            "kind": self.kind.value,
            "labels": list(self.labels),
        }
        if self.framework:
            data["framework"] = self.framework
        if self.precision:
            data["precision"] = self.precision
        return data


@dataclass
class PolyglotDependencyGraph:
    """In-memory polyglot dependency graph (imports + FFI + stubs)."""

    nodes: dict[str, TypedDependencyNode] = field(default_factory=dict)
    edges: list[TypedDependencyEdge] = field(default_factory=list)

    def add_node(self, node: TypedDependencyNode) -> TypedDependencyNode:
        """Insert or return an existing node with the same id."""
        existing = self.nodes.get(node.id)
        if existing is not None:
            return existing
        self.nodes[node.id] = node
        return node

    def add_edge(self, edge: TypedDependencyEdge) -> None:
        """Append an edge when source/target/kind are not already present."""
        for current in self.edges:
            if current.source == edge.source and current.target == edge.target and current.kind is edge.kind:
                return
        self.edges.append(edge)

    def edges_of_kind(self, kind: DependencyEdgeKind) -> tuple[TypedDependencyEdge, ...]:
        """Return edges matching ``kind``."""
        return tuple(e for e in self.edges if e.kind is kind)

    def successors(self, node_id: str, *, kind: DependencyEdgeKind | None = None) -> tuple[str, ...]:
        """Return targets of edges leaving ``node_id``."""
        out: list[str] = []
        for edge in self.edges:
            if edge.source != node_id:
                continue
            if kind is not None and edge.kind is not kind:
                continue
            out.append(edge.target)
        return tuple(out)

    def predecessors(self, node_id: str, *, kind: DependencyEdgeKind | None = None) -> tuple[str, ...]:
        """Return sources of edges entering ``node_id``."""
        out: list[str] = []
        for edge in self.edges:
            if edge.target != node_id:
                continue
            if kind is not None and edge.kind is not kind:
                continue
            out.append(edge.source)
        return tuple(out)

    def cross_language_neighbors(self, node_id: str) -> tuple[TypedDependencyEdge, ...]:
        """Return FFI / generated-from edges touching ``node_id``."""
        cross = {DependencyEdgeKind.FFI_BINDING, DependencyEdgeKind.GENERATED_FROM}
        return tuple(e for e in self.edges if e.kind in cross and (e.source == node_id or e.target == node_id))

    def to_json_obj(self) -> dict[str, Any]:
        """Return a JSON-serializable object."""
        return {
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges],
        }


def ingest_python_import_edges(
    graph: PolyglotDependencyGraph,
    *,
    edges: Iterable[tuple[str, str, tuple[str, ...]]],
) -> None:
    """Add ``PYTHON_IMPORT`` edges from ``(source, target, labels)`` triples."""
    for source, target, labels in edges:
        graph.add_node(TypedDependencyNode(id=source, language_id="python", kind="module", label=source))
        graph.add_node(TypedDependencyNode(id=target, language_id="python", kind="module", label=target))
        graph.add_edge(
            TypedDependencyEdge(
                source=source,
                target=target,
                kind=DependencyEdgeKind.PYTHON_IMPORT,
                labels=labels,
            )
        )


def ingest_binding_index(graph: PolyglotDependencyGraph, index: BindingIndex) -> None:
    """Project :class:`BindingIndex` into FFI / stub edges (evidence-backed only)."""
    for stub in index.stubs:
        _ingest_stub(graph, stub)
    for edge in index.edges:
        _ingest_binding_edge(graph, edge, index)


def _ingest_stub(graph: PolyglotDependencyGraph, stub: PyiStubSymbol) -> None:
    """Add a stub symbol node."""
    graph.add_node(
        TypedDependencyNode(
            id=stub.python_symbol,
            language_id="python",
            kind="stub",
            path=stub.uri,
            label=f"{stub.module}.{stub.name}",
        )
    )


def _ingest_binding_edge(
    graph: PolyglotDependencyGraph,
    edge: BindingEdge,
    index: BindingIndex,
) -> None:
    """Add FFI_BINDING and optional GENERATED_FROM (stub → FFI) edges."""
    py_id = edge.python_symbol
    native_id = edge.native_symbol
    graph.add_node(
        TypedDependencyNode(
            id=py_id,
            language_id="python",
            kind="symbol",
            label=edge.python_name or py_id,
        )
    )
    graph.add_node(
        TypedDependencyNode(
            id=native_id,
            language_id=edge.native_language_id or _language_from_native_key(native_id),
            kind="symbol",
            label=native_id,
        )
    )
    graph.add_edge(
        TypedDependencyEdge(
            source=py_id,
            target=native_id,
            kind=DependencyEdgeKind.FFI_BINDING,
            labels=(edge.framework.value, edge.precision.value),
            framework=edge.framework.value,
            precision=edge.precision.value,
        )
    )
    # Stub bridge: .pyi decl → same python symbol (GENERATED_FROM / bridge).
    for stub in index.stubs:
        if stub.python_symbol == py_id or (stub.module == edge.python_module and stub.name == edge.python_name):
            graph.add_node(
                TypedDependencyNode(
                    id=stub.python_symbol,
                    language_id="python",
                    kind="stub",
                    path=stub.uri,
                    label=f"{stub.module}.{stub.name}",
                )
            )
            if stub.python_symbol != py_id:
                graph.add_edge(
                    TypedDependencyEdge(
                        source=stub.python_symbol,
                        target=py_id,
                        kind=DependencyEdgeKind.GENERATED_FROM,
                        labels=("pyi",),
                        precision=BindingPrecision.BRIDGE.value,
                    )
                )
            break


def _language_from_native_key(native_symbol: str) -> str:
    """Infer language_id from ``rust:…`` / ``cpp:…`` keys."""
    if native_symbol.startswith("rust:"):
        return "rust"
    if native_symbol.startswith("cpp:"):
        return "cpp"
    return "unknown"


def build_polyglot_graph_from_bindings(index: BindingIndex) -> PolyglotDependencyGraph:
    """Convenience: BindingIndex → :class:`PolyglotDependencyGraph`."""
    graph = PolyglotDependencyGraph()
    ingest_binding_index(graph, index)
    return graph


__all__ = [
    "DependencyEdgeKind",
    "PolyglotDependencyGraph",
    "TypedDependencyEdge",
    "TypedDependencyNode",
    "build_polyglot_graph_from_bindings",
    "ingest_binding_index",
    "ingest_python_import_edges",
]
