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
    """One text edit bound to a document URI (rename / format preview)."""

    uri: str
    edit: TextEdit


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
