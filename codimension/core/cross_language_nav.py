# -*- coding: utf-8 -*-
#
# codimension - cross-language navigation (R207)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Cross-language navigation over BindingIndex + typed dependency edges (R207).

Typical chain::

    python caller / import
        → python:.pyi stub declaration
        → FFI binding edge (evidence-backed)
        → rust/cpp implementation

Navigation never invents exact FFI hops from matching names alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .bindings import BindingIndex
from .dependency_edges import (
    DependencyEdgeKind,
    PolyglotDependencyGraph,
    build_polyglot_graph_from_bindings,
)
from .symbol_index import SourceSpan


@dataclass(frozen=True, slots=True)
class NavigationHop:
    """One hop in a cross-language navigation path."""

    symbol: str
    language_id: str
    role: str
    edge_kind: DependencyEdgeKind | None = None
    uri: str = ""
    span: SourceSpan | None = None
    detail: str = ""


def navigate_python_export_to_native(
    index: BindingIndex,
    python_name: str,
    *,
    graph: PolyglotDependencyGraph | None = None,
) -> tuple[NavigationHop, ...]:
    """Build a hop list from a Python export name to its native implementation.

    Returns an empty tuple when no evidence-backed FFI edge exists.
    When a ``.pyi`` stub is present, it is inserted before the FFI hop.
    """
    stub, edges = index.bridge_chain_for(python_name)
    if not edges:
        return ()

    g = graph if graph is not None else build_polyglot_graph_from_bindings(index)
    hops: list[NavigationHop] = []

    if stub is not None:
        hops.append(
            NavigationHop(
                symbol=stub.python_symbol,
                language_id="python",
                role="pyi_stub",
                edge_kind=DependencyEdgeKind.GENERATED_FROM,
                uri=stub.uri,
                span=stub.span,
                detail=f"{stub.module}.{stub.name}",
            )
        )

    edge = edges[0]
    hops.append(
        NavigationHop(
            symbol=edge.python_symbol,
            language_id="python",
            role="python_export",
            edge_kind=DependencyEdgeKind.FFI_BINDING,
            detail=edge.python_name or python_name,
        )
    )

    evidence_uri = edge.evidence[0].uri if edge.evidence else ""
    evidence_span = edge.evidence[0].span if edge.evidence else None
    hops.append(
        NavigationHop(
            symbol=edge.native_symbol,
            language_id=edge.native_language_id or "unknown",
            role="native_impl",
            edge_kind=DependencyEdgeKind.FFI_BINDING,
            uri=evidence_uri,
            span=evidence_span,
            detail=f"{edge.framework.value}/{edge.precision.value}",
        )
    )

    # Ensure graph knows the FFI link (callers may pass a pre-built graph).
    _ = g.cross_language_neighbors(edge.python_symbol)
    return tuple(hops)


def navigate_native_to_python(
    index: BindingIndex,
    native_symbol: str,
) -> tuple[NavigationHop, ...]:
    """Reverse navigation: native symbol → Python export (and stub if any)."""
    edges = index.by_native_symbol(native_symbol)
    if not edges:
        return ()
    edge = edges[0]
    hops: list[NavigationHop] = [
        NavigationHop(
            symbol=edge.native_symbol,
            language_id=edge.native_language_id or "unknown",
            role="native_impl",
            edge_kind=DependencyEdgeKind.FFI_BINDING,
            detail=f"{edge.framework.value}/{edge.precision.value}",
        ),
        NavigationHop(
            symbol=edge.python_symbol,
            language_id="python",
            role="python_export",
            edge_kind=DependencyEdgeKind.FFI_BINDING,
            detail=edge.python_name,
        ),
    ]
    stub = next(
        (s for s in index.stubs if s.python_symbol == edge.python_symbol or s.name == edge.python_name),
        None,
    )
    if stub is not None:
        hops.append(
            NavigationHop(
                symbol=stub.python_symbol,
                language_id="python",
                role="pyi_stub",
                edge_kind=DependencyEdgeKind.GENERATED_FROM,
                uri=stub.uri,
                span=stub.span,
                detail=f"{stub.module}.{stub.name}",
            )
        )
    return tuple(hops)


def resolve_cross_language_target(
    index: BindingIndex,
    *,
    from_symbol: str,
    toward: str = "native",
) -> Optional[NavigationHop]:
    """Return the terminal hop for ``from_symbol`` toward ``native`` or ``python``.

    ``from_symbol`` may be a Python export name, ``python:module.name`` key, or
    a ``rust:`` / ``cpp:`` native key.
    """
    toward_norm = toward.strip().lower()
    if toward_norm == "native":
        name = from_symbol.rsplit(".", 1)[-1]
        hops = navigate_python_export_to_native(index, name)
        return hops[-1] if hops else None
    if toward_norm == "python":
        hops = navigate_native_to_python(index, from_symbol)
        if not hops:
            return None
        for hop in reversed(hops):
            if hop.role in {"pyi_stub", "python_export"}:
                return hop
        return hops[-1]
    raise ValueError(f"toward must be 'native' or 'python', got {toward!r}")


__all__ = [
    "NavigationHop",
    "navigate_native_to_python",
    "navigate_python_export_to_native",
    "resolve_cross_language_target",
]
