# -*- coding: utf-8 -*-
#
# codimension - polyglot structural graph contracts (R205)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""StructuralGraph + StructuralProvider (R205).

Tree-sitter (or another CST) yields a **syntax structural graph**, not a
compiler CFG: no type resolution, no macro expansion, no real control-flow
edges from the language semantics. Nodes carry ``native_kind`` (language
grammar type) and a shared :class:`SemanticRole` for polyglot UI geometry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable

from .document_snapshot import DocumentSnapshot
from .symbol_index import SourceSpan


class SemanticRole(str, Enum):
    """Shared visual / layout role across languages."""

    MODULE = "module"
    NAMESPACE = "namespace"
    IMPORT = "import"
    TYPE = "type"
    TRAIT = "trait"
    IMPL = "impl"
    FUNCTION = "function"
    CLOSURE = "closure"
    BRANCH = "branch"
    LOOP = "loop"
    RETURN = "return"
    BREAK = "break"
    CONTINUE = "continue"
    EARLY_EXIT = "early_exit"
    EXCEPTION_EXIT = "exception_exit"
    UNSAFE = "unsafe"
    AWAIT = "await"
    MACRO = "macro"
    FFI_BOUNDARY = "ffi_boundary"
    BLOCK = "block"
    OTHER = "other"


class StructuralEdgeKind(str, Enum):
    """Directed structural relationships (containment, not CFG successors)."""

    CONTAINS = "contains"


@dataclass(frozen=True, slots=True)
class StructuralNode:
    """One structural node with native grammar kind + shared semantic role."""

    id: str
    native_kind: str
    semantic_role: SemanticRole
    span: SourceSpan
    label: str = ""
    parent_id: str | None = None


@dataclass(frozen=True, slots=True)
class StructuralEdge:
    """Directed structural edge ``src -> dst``."""

    src: str
    dst: str
    kind: StructuralEdgeKind = StructuralEdgeKind.CONTAINS


@dataclass
class StructuralGraph:
    """In-memory structural graph for one document (not a compiler CFG)."""

    language_id: str
    nodes: dict[str, StructuralNode] = field(default_factory=dict)
    edges: list[StructuralEdge] = field(default_factory=list)
    root_id: str = ""
    errors: tuple[str, ...] = ()

    def children(self, node_id: str) -> tuple[str, ...]:
        """Return containment children of ``node_id``."""
        return tuple(e.dst for e in self.edges if e.src == node_id and e.kind == StructuralEdgeKind.CONTAINS)

    def nodes_of_role(self, role: SemanticRole) -> tuple[StructuralNode, ...]:
        """Return nodes matching ``role`` in insertion order."""
        return tuple(n for n in self.nodes.values() if n.semantic_role == role)


@runtime_checkable
class StructuralProvider(Protocol):
    """Language-neutral structural surface (typically Tree-sitter-backed)."""

    @property
    def provider_id(self) -> str:
        """Stable provider id (e.g. ``tree-sitter.rust``)."""

    @property
    def language_id(self) -> str:
        """Language id this provider builds graphs for."""

    def build_graph(self, document: DocumentSnapshot) -> StructuralGraph:
        """Build a structural graph for ``document`` (Unicode spans)."""


__all__ = [
    "SemanticRole",
    "StructuralEdge",
    "StructuralEdgeKind",
    "StructuralGraph",
    "StructuralNode",
    "StructuralProvider",
]
