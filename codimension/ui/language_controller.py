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

"""LanguageController: polyglot editor actions via capabilities only (R204 / R229 / R242 / R245).

No language-id branching in control flow. Actions resolve a
:class:`~core.language.LanguageService` by ``language_id`` or file extension,
then gate on :class:`~core.language.LanguageCapability` and an optional
:class:`~core.semantic.SemanticProvider`.

R229: ``supports()`` requires a bound semantic provider for every
semantic-backed capability (including ``DIAGNOSTICS``) — advertising alone
is not enough when the provider cannot serve the API.

R242: buffer open/change/close sync into the workspace
:class:`~core.document_store.DocumentStore` and optional
``sync_document`` / ``close_document`` on the bound provider.

R245: editor-owned monotonic versions; query snapshots must not regress to
``0``; Save As migrates ``close(old_uri) → open(new_uri)``.
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
from infrastructure.file_uri import path_to_file_uri


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
        """True when a matching service advertises ``capability`` and can serve it.

        Structural / FFI / build caps need only advertisement (providers are
        bound when those caps are set). Semantic-backed caps require a bound
        :class:`~core.semantic.SemanticProvider` (R229).
        """
        service = self.service_for_document(document)
        if service is None:
            return False
        if not service.has_capability(capability):
            return False
        if capability in {
            LanguageCapability.STRUCTURAL_GRAPH,
            LanguageCapability.FFI_BINDINGS,
            LanguageCapability.BUILD_TASKS,
        }:
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

    def language_id_for_uri(self, uri: str) -> str:
        """Return a registered ``language_id`` for ``uri``'s extension, or ``\"\"``."""
        ext = _extension_from_uri(uri)
        if not ext:
            return ""
        for service in self._manager.registry.list_services():
            if ext in service.descriptor.extensions:
                return str(service.descriptor.language_id)
        return ""

    def snapshot_for_buffer(
        self,
        *,
        path: str,
        text: str,
        version: int | None = None,
        language_id: str = "",
    ) -> DocumentSnapshot | None:
        """Build a :class:`DocumentSnapshot` for an absolute editor path.

        When ``version`` is ``None``, bump from the store (change path). Callers
        that only *query* semantics must pass the editor-owned version (R245)
        — never hardcode ``0`` after prior edits.
        """
        if not path or not os.path.isabs(path):
            return None
        uri = path_to_file_uri(path)
        lid = (language_id or "").strip() or self.language_id_for_uri(uri)
        if version is None:
            store = self._manager.document_store
            prev = store.get(uri) if store is not None else None
            version = (prev.version + 1) if prev is not None else 0
        return DocumentSnapshot(uri=uri, text=text, version=int(version), language_id=lid)

    def current_snapshot_for_buffer(
        self,
        *,
        path: str,
        text: str,
        language_id: str = "",
    ) -> DocumentSnapshot | None:
        """Build a snapshot that reuses the store version without bumping (R245).

        Used for capability probes and read-only semantic queries when the
        caller has no editor-owned counter. Never invents a regressive ``0``
        when the store already holds a higher version.
        """
        if not path or not os.path.isabs(path):
            return None
        uri = path_to_file_uri(path)
        lid = (language_id or "").strip() or self.language_id_for_uri(uri)
        store = self._manager.document_store
        prev = store.get(uri) if store is not None else None
        version = int(prev.version) if prev is not None else 0
        return DocumentSnapshot(uri=uri, text=text, version=version, language_id=lid)

    def notify_buffer_opened(self, document: DocumentSnapshot) -> None:
        """Publish an open buffer into the workspace store and sync the provider."""
        store = self._manager.document_store
        if store is not None:
            store.put_buffer(document)
        self._notify_semantic_sync(document)

    def notify_buffer_changed(self, document: DocumentSnapshot) -> None:
        """Publish a changed buffer (versioned) into the workspace store."""
        store = self._manager.document_store
        if store is not None:
            store.put_buffer(document)
        self._notify_semantic_sync(document)

    def notify_buffer_closed(self, uri: str) -> None:
        """Drop an open buffer and notify the semantic provider of close."""
        store = self._manager.document_store
        prev = store.get(uri) if store is not None else None
        if store is not None:
            store.discard(uri)
            if prev is not None and prev.uri != uri:
                store.discard(prev.uri)
        if prev is not None:
            self._notify_semantic_close(prev)

    def migrate_buffer(self, *, old_uri: str | None, document: DocumentSnapshot) -> None:
        """Atomically move an open buffer to a new URI (Save As / rename, R245).

        Closes ``old_uri`` when it differs from ``document.uri``, then opens
        the new snapshot. Same-URI calls are a no-op close and a fresh open.
        """
        old = (old_uri or "").strip()
        if old and old != document.uri:
            self.notify_buffer_closed(old)
        self.notify_buffer_opened(document)

    def _notify_semantic_sync(self, document: DocumentSnapshot) -> None:
        service = self.service_for_document(document)
        if service is None or service.semantic is None:
            return
        sync = getattr(service.semantic, "sync_document", None)
        if callable(sync):
            sync(document)

    def _notify_semantic_close(self, document: DocumentSnapshot) -> None:
        service = self.service_for_document(document)
        if service is None or service.semantic is None:
            return
        close = getattr(service.semantic, "close_document", None)
        if callable(close):
            close(document)

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
