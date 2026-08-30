# -*- coding: utf-8 -*-
#
# codimension - evidence-backed FFI BindingIndex (R206)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""BindingIndex + BindingProvider contracts (R206).

Edges require **evidence** (attribute / ``m.def`` / ``PyMethodDef`` / stub span).
Exact edges must never be invented from name equality alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Protocol, runtime_checkable

from .symbol_index import SourceSpan


class BindingFramework(str, Enum):
    """FFI framework that produced the evidence."""

    PYO3 = "pyo3"
    PYBIND11 = "pybind11"
    CPYTHON = "cpython"
    PYI = "pyi"


class BindingPrecision(str, Enum):
    """How precise the native target is."""

    EXACT = "exact"
    INLINE = "inline"
    BRIDGE = "bridge"


class BindingEvidenceKind(str, Enum):
    """Stable evidence tags stored on an edge."""

    PYFUNCTION_ATTR = "pyfunction_attr"
    PYO3_NAME_ATTR = "pyo3_name_attr"
    WRAP_PYFUNCTION = "wrap_pyfunction"
    PYMODULE_ATTR = "pymodule_attr"
    PYBIND11_MODULE = "pybind11_module"
    PYBIND11_DEF = "pybind11_def"
    PYBIND11_INLINE = "pybind11_inline"
    PYMETHODDEF = "pymethoddef"
    PYINIT = "pyinit"
    PYI_DECL = "pyi_decl"
    PYTHON_IMPORT = "python_import"


@dataclass(frozen=True, slots=True)
class BindingEvidence:
    """One located piece of evidence supporting an FFI edge."""

    kind: BindingEvidenceKind
    uri: str
    span: SourceSpan
    detail: str = ""


@dataclass(frozen=True, slots=True)
class BindingEdge:
    """Evidence-backed Python API ↔ native implementation edge."""

    python_symbol: str
    native_symbol: str
    framework: BindingFramework
    precision: BindingPrecision
    evidence: tuple[BindingEvidence, ...]
    python_module: str = ""
    python_name: str = ""
    native_language_id: str = ""
    provider_id: str = ""

    def __post_init__(self) -> None:
        """Reject empty symbols or exact edges without evidence."""
        if not self.python_symbol.strip():
            raise ValueError("python_symbol must be non-empty")
        if not self.native_symbol.strip():
            raise ValueError("native_symbol must be non-empty")
        if not self.evidence:
            raise ValueError("BindingEdge requires at least one evidence item")
        if self.precision is BindingPrecision.EXACT and not self.evidence:
            raise ValueError("exact BindingEdge requires evidence")


@dataclass(frozen=True, slots=True)
class PyiStubSymbol:
    """Declaration extracted from a ``.pyi`` stub (bridge side of the chain)."""

    module: str
    name: str
    uri: str
    span: SourceSpan
    kind: str = "function"

    @property
    def python_symbol(self) -> str:
        """Stable python-side key ``python:<module>.<name>``."""
        return f"python:{self.module}.{self.name}"


class ExactBindingWithoutEvidenceError(ValueError):
    """Raised when a caller attempts an exact edge with no evidence."""


@dataclass
class BindingIndex:
    """In-memory index of evidence-backed FFI edges + optional ``.pyi`` stubs."""

    edges: list[BindingEdge] = field(default_factory=list)
    stubs: list[PyiStubSymbol] = field(default_factory=list)

    def add_edge(self, edge: BindingEdge) -> None:
        """Append a validated :class:`BindingEdge`."""
        if not isinstance(edge, BindingEdge):
            raise TypeError(f"expected BindingEdge, got {type(edge)!r}")
        self.edges.append(edge)

    def add_edges(self, edges: Iterable[BindingEdge]) -> None:
        """Append many edges."""
        for edge in edges:
            self.add_edge(edge)

    def add_stub(self, stub: PyiStubSymbol) -> None:
        """Record a ``.pyi`` declaration for later bridge linking."""
        self.stubs.append(stub)

    def reject_name_only_exact(
        self,
        *,
        python_symbol: str,
        native_symbol: str,
        framework: BindingFramework,
    ) -> None:
        """Explicitly refuse creating an exact edge from names alone."""
        raise ExactBindingWithoutEvidenceError(
            f"refusing exact {framework.value} edge {python_symbol!r} → {native_symbol!r} "
            "without evidence (name equality is not enough)"
        )

    def by_python_name(self, name: str) -> tuple[BindingEdge, ...]:
        """Return edges whose Python export name matches ``name``."""
        return tuple(e for e in self.edges if e.python_name == name or e.python_symbol.endswith(f".{name}"))

    def by_python_symbol(self, symbol: str) -> tuple[BindingEdge, ...]:
        """Return edges with exact ``python_symbol``."""
        return tuple(e for e in self.edges if e.python_symbol == symbol)

    def by_native_symbol(self, symbol: str) -> tuple[BindingEdge, ...]:
        """Return edges with exact ``native_symbol``."""
        return tuple(e for e in self.edges if e.native_symbol == symbol)

    def stubs_for_module(self, module: str) -> tuple[PyiStubSymbol, ...]:
        """Return stub symbols declared for ``module``."""
        return tuple(s for s in self.stubs if s.module == module)

    def bridge_chain_for(self, python_name: str) -> tuple[PyiStubSymbol | None, tuple[BindingEdge, ...]]:
        """Return ``(.pyi`` stub if any, FFI edges) for a Python export name.

        Cross-language navigation (R207) builds on this chain; R206 only indexes it.
        """
        stub = next((s for s in self.stubs if s.name == python_name), None)
        edges = self.by_python_name(python_name)
        return stub, edges


@runtime_checkable
class BindingProvider(Protocol):
    """Extract evidence-backed binding edges from a source document."""

    @property
    def provider_id(self) -> str:
        """Stable provider id (e.g. ``ffi.pyo3``)."""

    @property
    def framework(self) -> BindingFramework:
        """Framework this provider understands."""

    def extract(self, uri: str, text: str) -> tuple[BindingEdge, ...]:
        """Parse ``text`` and return edges (never name-only exact)."""


__all__ = [
    "BindingEdge",
    "BindingEvidence",
    "BindingEvidenceKind",
    "BindingFramework",
    "BindingIndex",
    "BindingPrecision",
    "BindingProvider",
    "ExactBindingWithoutEvidenceError",
    "PyiStubSymbol",
]
