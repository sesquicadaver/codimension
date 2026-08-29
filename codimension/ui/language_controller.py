# -*- coding: utf-8 -*-
#
# codimension - capability-driven language UI controller (R204)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""LanguageController: polyglot editor actions via capabilities only (R204).

No language-id branching in control flow. Actions resolve a
:class:`~core.language.LanguageService` by ``language_id`` or file extension,
then gate on :class:`~core.language.LanguageCapability` and an optional
:class:`~core.semantic.SemanticProvider`.

This module is Qt-free so unit tests and headless tooling can drive it; MainWindow
wires results into widgets separately.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import cast
from urllib.parse import unquote, urlparse

from app.language_services import LanguageServiceManager
from core.document_snapshot import DocumentSnapshot
from core.language import LanguageCapability, LanguageService
from core.semantic import (
    HoverInfo,
    OutlineSymbol,
    SemanticProvider,
    SemanticReadiness,
    SymbolLocation,
    WorkspaceTextEdit,
)


class CapabilityDenied(RuntimeError):
    """Raised when an action is not advertised or has no semantic provider."""

    def __init__(self, message: str, *, capability: LanguageCapability | None = None) -> None:
        self.capability = capability
        super().__init__(message)


class DiagnosticsClaim(str, Enum):
    """How the UI may present diagnostics for the active language service."""

    FULL = "full"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class DiagnosticsPolicy:
    """Diagnostics access derived from capability + semantic readiness."""

    claim: DiagnosticsClaim
    readiness: SemanticReadiness | None
    reason: str


class LanguageController:
    """Capability-driven façade over :class:`LanguageServiceManager`."""

    def __init__(self, manager: LanguageServiceManager) -> None:
        """Bind to a language-services manager (owns registry + LSP processes)."""
        self._manager = manager

    @property
    def manager(self) -> LanguageServiceManager:
        """Underlying language services manager."""
        return self._manager

    def service_for_document(self, document: DocumentSnapshot) -> LanguageService | None:
        """Resolve a registered service by ``language_id`` or URI extension."""
        lang = (document.language_id or "").strip()
        if lang:
            found = self._manager.registry.get_by_language_id(lang)
            if found:
                return found[0]
        ext = _extension_from_uri(document.uri)
        if not ext:
            return None
        for service in self._manager.registry.list_services():
            if ext in service.descriptor.extensions:
                return service
        return None

    def supports(self, document: DocumentSnapshot, capability: LanguageCapability) -> bool:
        """True when a matching service advertises ``capability`` and can serve it."""
        service = self.service_for_document(document)
        if service is None:
            return False
        if not service.has_capability(capability):
            return False
        if capability is LanguageCapability.DIAGNOSTICS:
            return True
        return service.semantic is not None

    def diagnostics_policy(self, document: DocumentSnapshot) -> DiagnosticsPolicy:
        """Return how diagnostics may be claimed for ``document``."""
        service = self.service_for_document(document)
        if service is None:
            return DiagnosticsPolicy(
                claim=DiagnosticsClaim.UNAVAILABLE,
                readiness=None,
                reason="no language service for document",
            )
        if not service.has_capability(LanguageCapability.DIAGNOSTICS):
            return DiagnosticsPolicy(
                claim=DiagnosticsClaim.UNAVAILABLE,
                readiness=None,
                reason="DIAGNOSTICS capability not advertised",
            )
        semantic = service.semantic
        if semantic is None:
            return DiagnosticsPolicy(
                claim=DiagnosticsClaim.UNAVAILABLE,
                readiness=None,
                reason="no semantic provider",
            )
        readiness = semantic.readiness()
        if semantic.claims_full_diagnostics():
            return DiagnosticsPolicy(
                claim=DiagnosticsClaim.FULL,
                readiness=readiness,
                reason="semantic provider READY",
            )
        return DiagnosticsPolicy(
            claim=DiagnosticsClaim.DEGRADED,
            readiness=readiness,
            reason="semantic provider does not claim full diagnostics",
        )

    def hover(self, document: DocumentSnapshot, offset: int) -> HoverInfo | None:
        """Hover via capability-gated semantic provider."""
        semantic = self._require_semantic(document, LanguageCapability.HOVER)
        result = semantic.hover(document, offset)
        return result if result is None else HoverInfo(contents=result.contents, span=result.span)

    def definition(self, document: DocumentSnapshot, offset: int) -> tuple[SymbolLocation, ...]:
        """Go-to-definition via capability gate."""
        semantic = self._require_semantic(document, LanguageCapability.DEFINITION)
        return cast(tuple[SymbolLocation, ...], tuple(semantic.definition(document, offset)))

    def references(self, document: DocumentSnapshot, offset: int) -> tuple[SymbolLocation, ...]:
        """Find-references via capability gate."""
        semantic = self._require_semantic(document, LanguageCapability.REFERENCES)
        return cast(tuple[SymbolLocation, ...], tuple(semantic.references(document, offset)))

    def outline(self, document: DocumentSnapshot) -> tuple[OutlineSymbol, ...]:
        """Document outline via capability gate."""
        semantic = self._require_semantic(document, LanguageCapability.OUTLINE)
        return cast(tuple[OutlineSymbol, ...], tuple(semantic.document_symbols(document)))

    def format_preview(self, document: DocumentSnapshot) -> tuple[WorkspaceTextEdit, ...]:
        """Format preview edits (not applied)."""
        semantic = self._require_semantic(document, LanguageCapability.FORMAT)
        return cast(tuple[WorkspaceTextEdit, ...], tuple(semantic.format_document(document)))

    def rename_preview(
        self,
        document: DocumentSnapshot,
        offset: int,
        new_name: str,
    ) -> tuple[WorkspaceTextEdit, ...]:
        """Rename preview edits (not applied)."""
        if not new_name.strip():
            raise ValueError("new_name must be non-empty")
        semantic = self._require_semantic(document, LanguageCapability.RENAME)
        return cast(
            tuple[WorkspaceTextEdit, ...],
            tuple(semantic.rename_preview(document, offset, new_name)),
        )

    def _require_semantic(
        self,
        document: DocumentSnapshot,
        capability: LanguageCapability,
    ) -> SemanticProvider:
        service = self.service_for_document(document)
        if service is None:
            raise CapabilityDenied(
                "no language service registered for document",
                capability=capability,
            )
        if not service.has_capability(capability):
            raise CapabilityDenied(
                f"capability {capability.value!r} not advertised by {service.service_id}",
                capability=capability,
            )
        semantic = service.semantic
        if semantic is None:
            raise CapabilityDenied(
                f"service {service.service_id} has no semantic provider",
                capability=capability,
            )
        return semantic


def _extension_from_uri(uri: str) -> str:
    """Return lowercase file extension including the leading dot, or ``\"\"``."""
    path = uri
    if uri.startswith("file:"):
        parsed = urlparse(uri)
        path = unquote(parsed.path or "")
        # Windows file:///C:/... → /C:/...; keep as-is for splitext.
    _, ext = os.path.splitext(path)
    return ext.lower()


__all__ = [
    "CapabilityDenied",
    "DiagnosticsClaim",
    "DiagnosticsPolicy",
    "LanguageController",
]
