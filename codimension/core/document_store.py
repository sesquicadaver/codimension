# -*- coding: utf-8 -*-
#
# codimension - multi-document snapshot store (R224 / R235)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""DocumentStore: resolve URI → :class:`DocumentSnapshot` (R224 / R235 / R246).

LSP definition / references / rename often target a URI other than the
request document. Spans must be decoded against that target's text — not
against the current buffer.

R235: entries track ``OPEN_BUFFER`` vs ``DISK`` provenance with on-disk
identity (mtime/size/inode) so stale disk snapshots are reloaded; empty
stores stay truthy so ``document_store or DocumentStore(...)`` cannot
replace a shared workspace store; loaders are expected to be
workspace-bounded.

R246: ``file://`` path parsing percent-decodes so disk identity works for
canonical ``Path.as_uri()`` keys; disk entries without identity are not
treated as permanently fresh.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional
from urllib.parse import unquote, urlparse

from .document_snapshot import DocumentSnapshot

DocumentLoader = Callable[[str], Optional[DocumentSnapshot]]


class DocumentSource(str, Enum):
    """Where a stored snapshot came from."""

    OPEN_BUFFER = "open_buffer"
    DISK = "disk"


class ResolutionStatus(str, Enum):
    """Outcome of resolving a URI for span / edit decoding (R235)."""

    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class DiskIdentity:
    """Filesystem identity used to invalidate cached disk snapshots."""

    path: str
    mtime_ns: int
    size: int
    inode: int


@dataclass(slots=True)
class StoredDocument:
    """One URI entry in the store."""

    snapshot: DocumentSnapshot
    source: DocumentSource
    disk_identity: DiskIdentity | None = None


def capture_disk_identity(path: str) -> DiskIdentity | None:
    """Return :class:`DiskIdentity` for ``path``, or ``None`` on failure."""
    try:
        st = os.stat(path, follow_symlinks=True)
    except OSError:
        return None
    mtime_ns = int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000)))
    return DiskIdentity(
        path=os.path.realpath(path),
        mtime_ns=mtime_ns,
        size=int(st.st_size),
        inode=int(getattr(st, "st_ino", 0)),
    )


class DocumentStore:
    """In-memory URI → snapshot map with optional on-demand loading."""

    def __init__(self, *, loader: DocumentLoader | None = None) -> None:
        """Create an empty store; ``loader(uri)`` may populate misses."""
        self._docs: dict[str, StoredDocument] = {}
        self._loader = loader

    def __bool__(self) -> bool:
        """Always truthy so empty workspace stores are not replaced (R235)."""
        return True

    def put(self, document: DocumentSnapshot) -> None:
        """Insert or replace as an open-buffer snapshot (editor source of truth)."""
        self.put_buffer(document)

    def put_buffer(self, document: DocumentSnapshot) -> None:
        """Insert/replace ``document`` as :attr:`DocumentSource.OPEN_BUFFER`."""
        self._docs[document.uri] = StoredDocument(
            snapshot=document,
            source=DocumentSource.OPEN_BUFFER,
            disk_identity=None,
        )

    def put_disk(
        self,
        document: DocumentSnapshot,
        *,
        identity: DiskIdentity | None = None,
    ) -> None:
        """Insert/replace a disk-backed snapshot (may be invalidated on resolve)."""
        self._docs[document.uri] = StoredDocument(
            snapshot=document,
            source=DocumentSource.DISK,
            disk_identity=identity,
        )

    def discard(self, uri: str) -> None:
        """Drop a cached snapshot (e.g. after ``didClose``)."""
        self._docs.pop(uri, None)

    def clear(self) -> None:
        """Remove all cached snapshots."""
        self._docs.clear()

    def get(self, uri: str) -> DocumentSnapshot | None:
        """Return a cached snapshot only (no loader / no disk revalidation)."""
        entry = self._docs.get(uri)
        return None if entry is None else entry.snapshot

    def get_entry(self, uri: str) -> StoredDocument | None:
        """Return the full stored entry, if any."""
        return self._docs.get(uri)

    def resolve(self, uri: str) -> DocumentSnapshot | None:
        """Return a snapshot for ``uri``, revalidating disk entries and loading misses."""
        text = (uri or "").strip()
        if not text:
            return None
        entry = self._docs.get(text)
        if entry is not None:
            if entry.source is DocumentSource.OPEN_BUFFER:
                return entry.snapshot
            if entry.source is DocumentSource.DISK:
                if self._disk_entry_is_current(entry):
                    return entry.snapshot
                self._docs.pop(text, None)
                if entry.snapshot.uri != text:
                    self._docs.pop(entry.snapshot.uri, None)
        if self._loader is None:
            return None
        loaded = self._loader(text)
        if loaded is None:
            return None
        identity = self._identity_for_loaded(loaded.uri, text)
        stored = StoredDocument(
            snapshot=loaded,
            source=DocumentSource.DISK,
            disk_identity=identity,
        )
        self._docs[loaded.uri] = stored
        if loaded.uri != text:
            self._docs[text] = stored
        return loaded

    def resolve_status(self, uri: str) -> tuple[DocumentSnapshot | None, ResolutionStatus]:
        """Resolve ``uri`` and return ``(snapshot, status)`` (R235)."""
        snap = self.resolve(uri)
        if snap is None:
            return None, ResolutionStatus.UNRESOLVED
        return snap, ResolutionStatus.RESOLVED

    @staticmethod
    def _identity_for_loaded(loaded_uri: str, requested_uri: str) -> DiskIdentity | None:
        """Best-effort disk identity without importing infrastructure at module load."""
        path = _path_from_uri(loaded_uri) or _path_from_uri(requested_uri)
        if not path:
            return None
        return capture_disk_identity(path)

    @staticmethod
    def _disk_entry_is_current(entry: StoredDocument) -> bool:
        if entry.disk_identity is None:
            # R246: file:// without identity must not freeze as forever-fresh
            # (e.g. failed capture after percent-encoded path). Synthetic /
            # non-file URIs have no disk identity to refresh.
            if _path_from_uri(entry.snapshot.uri) is None:
                return True
            return False
        current = capture_disk_identity(entry.disk_identity.path)
        if current is None:
            return False
        return current == entry.disk_identity

    def __contains__(self, uri: object) -> bool:
        """True when ``uri`` is already cached (loader not consulted)."""
        return isinstance(uri, str) and uri in self._docs

    def __len__(self) -> int:
        """Number of cached documents."""
        return len(self._docs)


def _path_from_uri(uri: str) -> str | None:
    """Parse ``file://`` / absolute path with percent-decoding (R246).

    Kept in-core (no infrastructure import) to avoid cycles; semantics match
    :func:`infrastructure.file_uri.file_uri_to_path`.
    """
    text = (uri or "").strip()
    if not text:
        return None
    if text.startswith("file:"):
        parsed = urlparse(text)
        if parsed.scheme != "file":
            return None
        authority = (parsed.netloc or "").strip().lower()
        if authority not in ("", "localhost"):
            return None
        path = unquote(parsed.path or "")
        return path or None
    if os.path.isabs(text):
        return text
    return None


__all__ = [
    "DiskIdentity",
    "DocumentLoader",
    "DocumentSource",
    "DocumentStore",
    "ResolutionStatus",
    "StoredDocument",
    "capture_disk_identity",
]
