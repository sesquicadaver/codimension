# -*- coding: utf-8 -*-
"""R246: foreign URI boundary — UNRESOLVED gate, canonical URI, fd-rooted loader."""

from __future__ import annotations

import os
import stat
import time
from pathlib import Path

from core.document_store import DocumentStore, ResolutionStatus, _path_from_uri, capture_disk_identity
from core.semantic import SymbolLocation
from core.symbol_index import SourceSpan
from infrastructure.file_uri import (
    file_uri_to_path,
    load_document_from_uri,
    make_workspace_document_loader,
    path_to_file_uri,
)


def test_path_from_uri_percent_decodes() -> None:
    uri = "file:///tmp/my%20file.py"
    assert _path_from_uri(uri) == "/tmp/my file.py"
    assert file_uri_to_path(uri) == "/tmp/my file.py"


def test_percent_encoded_uri_disk_identity_and_stale_reload(tmp_path: Path) -> None:
    path = tmp_path / "my file.py"
    path.write_text("v1\n", encoding="utf-8")
    uri = path_to_file_uri(str(path))
    assert "%20" in uri or "my%20file" in uri
    assert capture_disk_identity(_path_from_uri(uri) or "") is not None

    store = DocumentStore(loader=make_workspace_document_loader(str(tmp_path)))
    first = store.resolve(uri)
    assert first is not None and first.text == "v1\n"
    entry = store.get_entry(uri) or store.get_entry(first.uri)
    assert entry is not None
    assert entry.disk_identity is not None
    assert " " in entry.disk_identity.path or entry.disk_identity.path.endswith("my file.py")

    path.write_text("v2\n", encoding="utf-8")
    # Ensure mtime advances on coarse filesystems.
    time.sleep(0.02)
    os.utime(path, None)
    second = store.resolve(uri)
    assert second is not None and second.text == "v2\n"


def test_symbol_location_unresolved_not_navigable() -> None:
    loc = SymbolLocation(
        uri="file:///tmp/secret.py",
        span=SourceSpan(0, 0),
        resolution_status=ResolutionStatus.UNRESOLVED,
    )
    assert loc.is_navigable() is False
    ok = SymbolLocation(
        uri="file:///tmp/ok.py",
        span=SourceSpan(0, 1),
        resolution_status=ResolutionStatus.RESOLVED,
    )
    assert ok.is_navigable() is True


def test_loader_rejects_outside_and_returns_canonical_uri(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("secret\n", encoding="utf-8")
    assert load_document_from_uri(path_to_file_uri(str(outside)), workspace_root=str(ws)) is None

    inside = ws / "ok.py"
    inside.write_text("ok\n", encoding="utf-8")
    snap = load_document_from_uri(path_to_file_uri(str(inside)), workspace_root=str(ws))
    assert snap is not None
    assert snap.text == "ok\n"
    assert snap.uri == path_to_file_uri(str(inside.resolve()))


def test_loader_rejects_fifo_without_blocking(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    fifo = ws / "pipe.fifo"
    os.mkfifo(fifo)
    assert stat.S_ISFIFO(os.stat(fifo).st_mode)

    started = time.monotonic()
    snap = load_document_from_uri(path_to_file_uri(str(fifo)), workspace_root=str(ws))
    elapsed = time.monotonic() - started
    assert snap is None
    assert elapsed < 1.0


def test_loader_rejects_symlink_escape_via_parent(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.py"
    secret.write_text("leak\n", encoding="utf-8")
    link = ws / "escape"
    link.symlink_to(outside, target_is_directory=True)

    uri = path_to_file_uri(str(link / "secret.py"))
    assert load_document_from_uri(uri, workspace_root=str(ws)) is None


def test_store_resolve_status_unresolved_outside(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    outside = tmp_path / "x.py"
    outside.write_text("x\n", encoding="utf-8")
    store = DocumentStore(loader=make_workspace_document_loader(str(ws)))
    snap, status = store.resolve_status(path_to_file_uri(str(outside)))
    assert snap is None
    assert status is ResolutionStatus.UNRESOLVED
