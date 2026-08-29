# -*- coding: utf-8 -*-
#
# codimension - headless SymbolIndex schema (R130)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""SymbolIndex schema + definition/reference queries (R130/R132).

Population from ``brief_ast`` is R131. This module is Qt-free and lives in
``core`` so headless tooling can depend on the schema alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Iterable, Iterator, Mapping, Optional, Sequence


def _empty_extras() -> Mapping[str, str]:
    """Return a fresh empty immutable extras mapping."""
    return MappingProxyType({})


class SymbolKind(str, Enum):
    """Stable kind tags for indexed definitions (extend in later tasks)."""

    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    VARIABLE = "variable"
    ATTRIBUTE = "attribute"
    IMPORT = "import"
    UNKNOWN = "unknown"


class GenericSymbolKind(str, Enum):
    """Language-neutral kind tags for polyglot UI (R200 additive)."""

    MODULE = "module"
    NAMESPACE = "namespace"
    TYPE = "type"
    ENUM = "enum"
    TRAIT = "trait"
    FUNCTION = "function"
    METHOD = "method"
    FIELD = "field"
    VARIABLE = "variable"
    CONSTANT = "constant"
    MACRO = "macro"
    IMPORT = "import"
    UNKNOWN = "unknown"


_SYMBOL_KIND_TO_GENERIC: dict[SymbolKind, GenericSymbolKind] = {
    SymbolKind.MODULE: GenericSymbolKind.MODULE,
    SymbolKind.CLASS: GenericSymbolKind.TYPE,
    SymbolKind.FUNCTION: GenericSymbolKind.FUNCTION,
    SymbolKind.METHOD: GenericSymbolKind.METHOD,
    SymbolKind.VARIABLE: GenericSymbolKind.VARIABLE,
    SymbolKind.ATTRIBUTE: GenericSymbolKind.FIELD,
    SymbolKind.IMPORT: GenericSymbolKind.IMPORT,
    SymbolKind.UNKNOWN: GenericSymbolKind.UNKNOWN,
}


def generic_kind_for_symbol_kind(kind: SymbolKind) -> GenericSymbolKind:
    """Map a Python-oriented :class:`SymbolKind` to :class:`GenericSymbolKind`."""
    return _SYMBOL_KIND_TO_GENERIC.get(kind, GenericSymbolKind.UNKNOWN)


# Kinds treated as definitions by ``find_definitions`` (imports are references).
DEFINITION_KINDS: frozenset[SymbolKind] = frozenset(
    {
        SymbolKind.MODULE,
        SymbolKind.CLASS,
        SymbolKind.FUNCTION,
        SymbolKind.METHOD,
        SymbolKind.VARIABLE,
        SymbolKind.ATTRIBUTE,
        SymbolKind.UNKNOWN,
    }
)


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """Half-open character span ``[start, end)`` in a decoded source string.

    Offsets are 0-based Unicode character indices (same convention as
    ``parsers.source_spans``). ``end`` is exclusive.
    """

    start: int
    end: int

    def __post_init__(self) -> None:
        """Reject negative or inverted spans."""
        if self.start < 0:
            raise ValueError(f"span start must be >= 0, got {self.start}")
        if self.end < self.start:
            raise ValueError(f"span end {self.end} must be >= start {self.start}")

    @property
    def length(self) -> int:
        """Number of characters covered by the span."""
        return self.end - self.start

    def contains(self, offset: int) -> bool:
        """Return True if ``offset`` lies in ``[start, end)``."""
        return self.start <= offset < self.end

    def overlaps(self, other: SourceSpan) -> bool:
        """Return True if the half-open intervals intersect."""
        return self.start < other.end and other.start < self.end


@dataclass(frozen=True, slots=True)
class SymbolRecord:
    """One indexed definition / symbol occurrence.

    Attributes:
        name: Unqualified symbol name (e.g. ``MyClass``, ``foo``).
        kind: Symbol classification (Python-oriented; kept for compatibility).
        file: Project-relative or absolute path to the defining file.
        span: Half-open character span of the defining name (or header).
        container: Optional qualified parent (e.g. ``pkg.mod.MyClass``);
            ``None`` for module-level symbols.
        qualname: Optional fully-qualified name; when omitted, derived as
            ``container.name`` or ``name``.
        line: Optional 1-based source line (from brief_ast) for search bridges.
        extras: Immutable optional metadata bag for later tasks.
        language_id: Polyglot language id (R200; default ``python``).
        generic_kind: Language-neutral kind (R200; derived from ``kind``).
        symbol_key: Stable cross-provider key (R200; derived when omitted).
        provider_id: Indexing provider id (R200; default ``python.brief``).
        native_kind: Language-specific kind tag (R200; e.g. ``python.class``).
    """

    name: str
    kind: SymbolKind
    file: str
    span: SourceSpan
    container: Optional[str] = None
    qualname: Optional[str] = None
    line: Optional[int] = None
    extras: Mapping[str, str] = field(default_factory=_empty_extras)
    language_id: str = "python"
    generic_kind: Optional[GenericSymbolKind] = None
    symbol_key: Optional[str] = None
    provider_id: str = "python.brief"
    native_kind: Optional[str] = None

    def __post_init__(self) -> None:
        """Normalize kind/extras and derive polyglot fields when missing."""
        if not self.name:
            raise ValueError("symbol name must be non-empty")
        if not self.file:
            raise ValueError("symbol file must be non-empty")
        kind = self.kind if isinstance(self.kind, SymbolKind) else SymbolKind(self.kind)
        object.__setattr__(self, "kind", kind)
        extras = MappingProxyType(dict(self.extras) if self.extras else {})
        object.__setattr__(self, "extras", extras)
        if self.qualname is None:
            if self.container:
                object.__setattr__(self, "qualname", f"{self.container}.{self.name}")
            else:
                object.__setattr__(self, "qualname", self.name)
        language_id = (self.language_id or "python").strip() or "python"
        object.__setattr__(self, "language_id", language_id)
        if self.generic_kind is None:
            object.__setattr__(self, "generic_kind", generic_kind_for_symbol_kind(kind))
        elif not isinstance(self.generic_kind, GenericSymbolKind):
            object.__setattr__(self, "generic_kind", GenericSymbolKind(self.generic_kind))
        if self.native_kind is None:
            object.__setattr__(self, "native_kind", f"{language_id}.{kind.value}")
        if self.symbol_key is None:
            object.__setattr__(
                self,
                "symbol_key",
                f"{language_id}:{self.file}:{self.qualname}:{kind.value}",
            )
        if not self.provider_id:
            object.__setattr__(self, "provider_id", "python.brief")


class SymbolIndex:
    """In-memory collection of ``SymbolRecord`` values (schema + basic access).

    Not a query engine — R132 adds ``find_definitions`` / ``find_references``.
    """

    def __init__(self, records: Optional[Iterable[SymbolRecord]] = None) -> None:
        """Optionally seed the index with an iterable of records."""
        self._records: list[SymbolRecord] = list(records) if records else []

    def __len__(self) -> int:
        return len(self._records)

    def __iter__(self) -> Iterator[SymbolRecord]:
        return iter(self._records)

    def add(self, record: SymbolRecord) -> None:
        """Append a validated symbol record."""
        if not isinstance(record, SymbolRecord):
            raise TypeError(f"expected SymbolRecord, got {type(record)!r}")
        self._records.append(record)

    def extend(self, records: Iterable[SymbolRecord]) -> None:
        """Append many records."""
        for record in records:
            self.add(record)

    def clear(self) -> None:
        """Remove all records."""
        self._records.clear()

    def symbols(self) -> Sequence[SymbolRecord]:
        """Return an immutable snapshot of all records."""
        return tuple(self._records)

    def by_name(self, name: str) -> tuple[SymbolRecord, ...]:
        """Return records whose unqualified ``name`` matches exactly."""
        return tuple(r for r in self._records if r.name == name)

    def by_file(self, file: str) -> tuple[SymbolRecord, ...]:
        """Return records defined in ``file`` (exact path match)."""
        return tuple(r for r in self._records if r.file == file)

    def by_kind(self, kind: SymbolKind) -> tuple[SymbolRecord, ...]:
        """Return records of the given kind."""
        return tuple(r for r in self._records if r.kind is kind)

    def by_container(self, container: Optional[str]) -> tuple[SymbolRecord, ...]:
        """Return records whose ``container`` equals ``container`` (incl. None)."""
        return tuple(r for r in self._records if r.container == container)

    def find_definitions(
        self,
        name: str,
        *,
        file: Optional[str] = None,
        kind: Optional[SymbolKind] = None,
        qualname: Optional[str] = None,
    ) -> tuple[SymbolRecord, ...]:
        """Return defining records for ``name`` (excludes import references).

        Filters are AND-combined. ``qualname`` matches the derived/fully
        qualified name exactly when provided.
        """
        out: list[SymbolRecord] = []
        for record in self._records:
            if record.name != name:
                continue
            if record.kind not in DEFINITION_KINDS:
                continue
            if file is not None and record.file != file:
                continue
            if kind is not None and record.kind is not kind:
                continue
            if qualname is not None and record.qualname != qualname:
                continue
            out.append(record)
        return tuple(out)

    def find_references(
        self,
        name: str,
        *,
        file: Optional[str] = None,
    ) -> tuple[SymbolRecord, ...]:
        """Return reference-like records for ``name``.

        MVP: ``IMPORT`` kind and any record with ``extras['role'] == 'reference'``.
        Full name-use analysis is deferred; search bridges may combine this with
        ``find_definitions`` for an occurrences-style report.
        """
        out: list[SymbolRecord] = []
        for record in self._records:
            if record.name != name:
                continue
            if file is not None and record.file != file:
                continue
            role = record.extras.get("role")
            if record.kind is SymbolKind.IMPORT or role == "reference":
                out.append(record)
        return tuple(out)


def build_symbol(
    name: str,
    kind: SymbolKind | str,
    file: str,
    start: int,
    end: int,
    *,
    container: Optional[str] = None,
    qualname: Optional[str] = None,
    line: Optional[int] = None,
    extras: Optional[Mapping[str, str]] = None,
    language_id: str = "python",
    generic_kind: Optional[GenericSymbolKind | str] = None,
    symbol_key: Optional[str] = None,
    provider_id: str = "python.brief",
    native_kind: Optional[str] = None,
) -> SymbolRecord:
    """Convenience constructor for a ``SymbolRecord`` with a half-open span."""
    gk: Optional[GenericSymbolKind]
    if generic_kind is None:
        gk = None
    elif isinstance(generic_kind, GenericSymbolKind):
        gk = generic_kind
    else:
        gk = GenericSymbolKind(generic_kind)
    return SymbolRecord(
        name=name,
        kind=SymbolKind(kind) if not isinstance(kind, SymbolKind) else kind,
        file=file,
        span=SourceSpan(start, end),
        container=container,
        qualname=qualname,
        line=line,
        extras=MappingProxyType(dict(extras) if extras else {}),
        language_id=language_id,
        generic_kind=gk,
        symbol_key=symbol_key,
        provider_id=provider_id,
        native_kind=native_kind,
    )
