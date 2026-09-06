# -*- coding: utf-8 -*-
#
# codimension - multi-document snapshot store (R224)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""DocumentStore: resolve URI → :class:`DocumentSnapshot` (R224).

LSP definition / references / rename often target a URI other than the
request document. Spans must be decoded against that target's text — not
against the current buffer (which produced ``SourceSpan(0, 0)`` placeholders).

The store keeps open/synced snapshots and optionally loads missing ``file://``
documents via an injectable loader (filesystem belongs outside ``core``).
"""

from __future__ import annotations

from typing import Callable, Optional

from .document_snapshot import DocumentSnapshot

DocumentLoader = Callable[[str], Optional[DocumentSnapshot]]


class DocumentStore:
    """In-memory URI → snapshot map with optional on-demand loading."""

    def __init__(self, *, loader: DocumentLoader | None = None) -> None:
        """Create an empty store; ``loader(uri)`` may populate misses."""
        self._docs: dict[str, DocumentSnapshot] = {}
        self._loader = loader

    def put(self, document: DocumentSnapshot) -> None:
        """Insert or replace the snapshot for ``document.uri``."""
        self._docs[document.uri] = document

    def discard(self, uri: str) -> None:
        """Drop a cached snapshot (e.g. after ``didClose``)."""
        self._docs.pop(uri, None)

    def clear(self) -> None:
        """Remove all cached snapshots."""
        self._docs.clear()

    def get(self, uri: str) -> DocumentSnapshot | None:
        """Return a cached snapshot only (no loader)."""
        return self._docs.get(uri)

    def resolve(self, uri: str) -> DocumentSnapshot | None:
        """Return a snapshot for ``uri``, loading via ``loader`` on cache miss."""
        text = (uri or "").strip()
        if not text:
            return None
        hit = self._docs.get(text)
        if hit is not None:
            return hit
        if self._loader is None:
            return None
        loaded = self._loader(text)
        if loaded is not None:
            self._docs[loaded.uri] = loaded
            if loaded.uri != text:
                # Also index under the requested key when loaders normalize URIs.
                self._docs[text] = loaded
        return loaded

    def __contains__(self, uri: object) -> bool:
        """True when ``uri`` is already cached (loader not consulted)."""
        return isinstance(uri, str) and uri in self._docs

    def __len__(self) -> int:
        """Number of cached documents."""
        return len(self._docs)


__all__ = [
    "DocumentLoader",
    "DocumentStore",
]
