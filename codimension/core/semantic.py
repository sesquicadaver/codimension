# -*- coding: utf-8 -*-
#
# codimension - polyglot semantic provider contracts (R203/R204)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""SemanticProvider protocol and readiness for LSP-backed languages (R203/R204).

Qt-free. UI must consult :meth:`SemanticProvider.readiness` before claiming
full diagnostics — C++ without ``compile_commands.json`` is
:attr:`SemanticReadiness.DEGRADED`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from .document_snapshot import DocumentSnapshot, TextEdit
from .document_store import ResolutionStatus
from .symbol_index import SourceSpan


class SemanticReadiness(str, Enum):
    """How complete semantic answers from a provider are."""

    READY = "ready"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class HoverInfo:
    """Hover payload in internal Unicode coordinates."""

    contents: str
    span: SourceSpan | None = None


@dataclass(frozen=True, slots=True)
class SymbolLocation:
    """Definition / reference location (Unicode span)."""

    uri: str
    span: SourceSpan
    resolution_status: ResolutionStatus = ResolutionStatus.RESOLVED

    def is_navigable(self) -> bool:
        """True when UI may open this location (R246 — reject UNRESOLVED)."""
        return self.resolution_status is ResolutionStatus.RESOLVED


@dataclass(frozen=True, slots=True)
class OutlineSymbol:
    """Document-symbol / outline entry."""

    name: str
    kind: str
    span: SourceSpan
    selection_span: SourceSpan | None = None
    children: tuple["OutlineSymbol", ...] = ()


@dataclass(frozen=True, slots=True)
class WorkspaceTextEdit:
    """One text edit bound to a document URI (rename / format preview).

    R235: ``expected_version`` and ``resolution_status`` gate apply; unresolved
    or stale edits must not be applied as if they were trusted ``(0, 0)`` spans.
    """

    uri: str
    edit: TextEdit
    expected_version: int | None = None
    resolution_status: ResolutionStatus = ResolutionStatus.RESOLVED

    def is_applicable(self, current_version: int | None = None) -> bool:
        """True when resolved and ``expected_version`` matches the live document (R235 / R251).

        ``expected_version`` must be set; callers pass the current DocumentStore
        version. Missing version or mismatch → not applicable (fail-closed).
        """
        if self.resolution_status is not ResolutionStatus.RESOLVED:
            return False
        if self.expected_version is None or current_version is None:
            return False
        return int(self.expected_version) == int(current_version)


@runtime_checkable
class SemanticProvider(Protocol):
    """Language-neutral semantic surface (typically LSP-backed)."""

    @property
    def provider_id(self) -> str:
        """Stable provider id (e.g. ``lsp.rust-analyzer``)."""

    def readiness(self) -> SemanticReadiness:
        """Return current semantic readiness."""

    def claims_full_diagnostics(self) -> bool:
        """True only when diagnostics may be treated as complete."""

    def hover(self, document: DocumentSnapshot, offset: int) -> HoverInfo | None:
        """Hover at Unicode ``offset``, or ``None``."""

    def definition(self, document: DocumentSnapshot, offset: int) -> tuple[SymbolLocation, ...]:
        """Go-to-definition locations."""

    def references(self, document: DocumentSnapshot, offset: int) -> tuple[SymbolLocation, ...]:
        """Find-references locations."""

    def document_symbols(self, document: DocumentSnapshot) -> tuple[OutlineSymbol, ...]:
        """Document outline symbols."""

    def format_document(self, document: DocumentSnapshot) -> tuple[WorkspaceTextEdit, ...]:
        """Format whole document → preview edits (not applied)."""

    def rename_preview(
        self,
        document: DocumentSnapshot,
        offset: int,
        new_name: str,
    ) -> tuple[WorkspaceTextEdit, ...]:
        """Rename preview edits (not applied)."""


__all__ = [
    "HoverInfo",
    "OutlineSymbol",
    "SemanticProvider",
    "SemanticReadiness",
    "SymbolLocation",
    "WorkspaceTextEdit",
]
