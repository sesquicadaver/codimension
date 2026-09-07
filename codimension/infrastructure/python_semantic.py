# -*- coding: utf-8 -*-
#
# codimension - Python headless SemanticProvider (R242)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Brief/SymbolIndex-backed :class:`~core.semantic.SemanticProvider` for Python (R242).

Binds the advertised ``OUTLINE`` / ``DEFINITION`` / ``REFERENCES`` capabilities
of ``python.headless`` to a real provider so
:meth:`ui.language_controller.LanguageController.supports` matches the registry.
"""

from __future__ import annotations

import re
from pathlib import Path

from core.document_snapshot import DocumentSnapshot
from core.document_store import ResolutionStatus
from core.semantic import (
    HoverInfo,
    OutlineSymbol,
    SemanticReadiness,
    SymbolLocation,
    WorkspaceTextEdit,
)
from core.symbol_index import SourceSpan, SymbolIndex, SymbolKind
from infrastructure.file_uri import file_uri_to_path, path_to_file_uri
from utils.symbol_index_brief import index_source

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def word_at_offset(text: str, offset: int) -> str:
    """Return the Python identifier covering Unicode ``offset``, or ``\"\"``."""
    if not text:
        return ""
    pos = max(0, min(int(offset), len(text)))
    if pos < len(text) and (text[pos].isalnum() or text[pos] == "_"):
        start = pos
    elif pos > 0 and (text[pos - 1].isalnum() or text[pos - 1] == "_"):
        start = pos - 1
    else:
        return ""
    while start > 0 and (text[start - 1].isalnum() or text[start - 1] == "_"):
        start -= 1
    end = start
    while end < len(text) and (text[end].isalnum() or text[end] == "_"):
        end += 1
    match = _IDENT.fullmatch(text[start:end])
    return str(match.group(0)) if match else ""


def _file_key(document: DocumentSnapshot) -> str:
    """Filesystem path when possible; otherwise the document URI."""
    path = file_uri_to_path(document.uri)
    if path:
        return str(Path(path).resolve())
    return str(document.uri)


def _uri_for_file(file_path: str, fallback_uri: str) -> str:
    if not file_path:
        return fallback_uri
    if file_path.startswith("file:"):
        return file_path
    try:
        return str(path_to_file_uri(file_path))
    except (OSError, ValueError):
        return fallback_uri


class PythonHeadlessSemanticProvider:
    """Qt-free Python semantic surface over brief_ast → SymbolIndex."""

    @property
    def provider_id(self) -> str:
        """Stable provider id."""
        return "python.headless.brief"

    def readiness(self) -> SemanticReadiness:
        """Headless brief analysis is always READY for advertised caps."""
        return SemanticReadiness.READY

    def claims_full_diagnostics(self) -> bool:
        """Python headless does not advertise DIAGNOSTICS."""
        return False

    def hover(self, document: DocumentSnapshot, offset: int) -> HoverInfo | None:
        """No hover in the headless MVP (capability not advertised)."""
        return None

    def definition(self, document: DocumentSnapshot, offset: int) -> tuple[SymbolLocation, ...]:
        """Go-to-definition via SymbolIndex for the identifier at ``offset``."""
        name = word_at_offset(document.text, offset)
        if not name:
            return ()
        index = self._index(document)
        defs = index.find_definitions(name)
        out: list[SymbolLocation] = []
        for record in defs:
            out.append(
                SymbolLocation(
                    uri=_uri_for_file(record.file, document.uri),
                    span=record.span,
                    resolution_status=ResolutionStatus.RESOLVED,
                )
            )
        return tuple(out)

    def references(self, document: DocumentSnapshot, offset: int) -> tuple[SymbolLocation, ...]:
        """Find references: SymbolIndex hits plus in-document identifier spans."""
        name = word_at_offset(document.text, offset)
        if not name:
            return ()
        index = self._index(document)
        hits = list(index.find_definitions(name)) + list(index.find_references(name))
        seen: set[tuple[str, int, int]] = set()
        out: list[SymbolLocation] = []
        for record in hits:
            uri = _uri_for_file(record.file, document.uri)
            key = (uri, record.span.start, record.span.end)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                SymbolLocation(
                    uri=uri,
                    span=record.span,
                    resolution_status=ResolutionStatus.RESOLVED,
                )
            )
        # Local textual occurrences (call sites / names not in brief index).
        for match in _IDENT.finditer(document.text):
            if match.group(0) != name:
                continue
            key = (document.uri, match.start(), match.end())
            if key in seen:
                continue
            seen.add(key)
            out.append(
                SymbolLocation(
                    uri=document.uri,
                    span=SourceSpan(match.start(), match.end()),
                    resolution_status=ResolutionStatus.RESOLVED,
                )
            )
        return tuple(out)

    def document_symbols(self, document: DocumentSnapshot) -> tuple[OutlineSymbol, ...]:
        """Outline from brief-derived function/class/method records."""
        index = self._index(document)
        out: list[OutlineSymbol] = []
        for record in index.symbols():
            if record.kind not in {
                SymbolKind.FUNCTION,
                SymbolKind.CLASS,
                SymbolKind.METHOD,
                SymbolKind.MODULE,
            }:
                continue
            out.append(
                OutlineSymbol(
                    name=record.name,
                    kind=record.kind.value,
                    span=record.span,
                    selection_span=record.span,
                )
            )
        return tuple(out)

    def format_document(self, document: DocumentSnapshot) -> tuple[WorkspaceTextEdit, ...]:
        """Format is not offered by the headless provider."""
        return ()

    def rename_preview(
        self,
        document: DocumentSnapshot,
        offset: int,
        new_name: str,
    ) -> tuple[WorkspaceTextEdit, ...]:
        """Rename is not offered by the headless provider."""
        return ()

    def sync_document(self, document: DocumentSnapshot) -> None:
        """No process to notify; DocumentStore is the buffer source of truth."""
        return None

    def close_document(self, document: DocumentSnapshot) -> None:
        """No process to notify on close."""
        return None

    def _index(self, document: DocumentSnapshot) -> SymbolIndex:
        file_key = _file_key(document)
        return SymbolIndex(index_source(document.text, file_key))


__all__ = [
    "PythonHeadlessSemanticProvider",
    "word_at_offset",
]
