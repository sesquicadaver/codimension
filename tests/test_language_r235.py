# -*- coding: utf-8 -*-
"""R235: workspace DocumentStore — identity, versioned edits, bounded loader."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from core.document_snapshot import DocumentSnapshot
from core.document_store import DocumentSource, DocumentStore, ResolutionStatus
from core.symbol_index import SourceSpan
from infrastructure.file_uri import (
    load_document_from_uri,
    make_workspace_document_loader,
    path_to_file_uri,
)
from infrastructure.lsp_position_codec import LspPositionCodec
from infrastructure.lsp_process import LspProcessRegistry
from infrastructure.lsp_semantic import (
    LspSemanticConfig,
    LspSemanticProvider,
    _parse_text_edits,
    _parse_workspace_edit,
)


def test_empty_document_store_is_truthy() -> None:
    store = DocumentStore()
    assert len(store) == 0
    assert bool(store) is True
    # Provider must keep a shared empty store (R235 P1-04.1).
    registry = LspProcessRegistry()
    config = LspSemanticConfig(
        language_id="rust",
        workspace_root="/tmp",
        command=("/bin/true",),
        allowlist=("/bin/true",),
    )
    provider = LspSemanticProvider(registry, config, document_store=store)
    assert provider.document_store is store


def test_open_buffer_beats_stale_disk(tmp_path: Path) -> None:
    path = tmp_path / "x.rs"
    path.write_text("disk\n", encoding="utf-8")
    uri = path_to_file_uri(str(path))
    store = DocumentStore(loader=make_workspace_document_loader(str(tmp_path)))
    disk = store.resolve(uri)
    assert disk is not None and disk.text == "disk\n"
    assert store.get_entry(uri) is not None
    assert store.get_entry(uri).source is DocumentSource.DISK

    buf = DocumentSnapshot(uri=uri, text="buffer\n", version=3, language_id="rust")
    store.put_buffer(buf)
    assert store.resolve(uri) is buf
    assert store.get_entry(uri).source is DocumentSource.OPEN_BUFFER


def test_disk_cache_reloads_after_mtime_change(tmp_path: Path) -> None:
    path = tmp_path / "y.rs"
    path.write_text("v1\n", encoding="utf-8")
    uri = path_to_file_uri(str(path))
    store = DocumentStore(loader=make_workspace_document_loader(str(tmp_path)))
    first = store.resolve(uri)
    assert first is not None and first.text == "v1\n"
    path.write_text("v2\n", encoding="utf-8")
    second = store.resolve(uri)
    assert second is not None and second.text == "v2\n"


def test_loader_rejects_outside_workspace(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    outside = tmp_path / "outside.rs"
    outside.write_text("secret\n", encoding="utf-8")
    uri = path_to_file_uri(str(outside))
    assert load_document_from_uri(uri, workspace_root=str(ws)) is None
    inside = ws / "ok.rs"
    inside.write_text("ok\n", encoding="utf-8")
    snap = load_document_from_uri(path_to_file_uri(str(inside)), workspace_root=str(ws))
    assert snap is not None and snap.text == "ok\n"


def test_loader_rejects_oversized(tmp_path: Path) -> None:
    path = tmp_path / "big.rs"
    path.write_bytes(b"x" * 100)
    uri = path_to_file_uri(str(path))
    assert load_document_from_uri(uri, workspace_root=str(tmp_path), max_bytes=50) is None


def test_loader_rejects_remote_authority() -> None:
    assert load_document_from_uri("file://evil.example/etc/passwd") is None


def test_workspace_edit_keeps_version_and_denies_unresolved() -> None:
    codec = LspPositionCodec()
    current = DocumentSnapshot(uri="file:///tmp/a.rs", text="fn a() {}\n", version=1)
    foreign = DocumentSnapshot(uri="file:///tmp/b.rs", text="fn b() {}\n", version=7)
    store = DocumentStore()
    store.put_buffer(foreign)
    proc = SimpleNamespace(codec=codec)

    edits = _parse_workspace_edit(
        proc,  # type: ignore[arg-type]
        current,
        {
            "documentChanges": [
                {
                    "textDocument": {"uri": foreign.uri, "version": 7},
                    "edits": [
                        {
                            "range": {
                                "start": {"line": 0, "character": 3},
                                "end": {"line": 0, "character": 4},
                            },
                            "newText": "c",
                        }
                    ],
                }
            ]
        },
        store=store,
    )
    assert len(edits) == 1
    assert edits[0].expected_version == 7
    assert edits[0].is_applicable(7)
    assert edits[0].is_applicable(8) is False
    assert edits[0].is_applicable() is False
    assert edits[0].edit.span == SourceSpan(3, 4)

    missing = _parse_text_edits(
        proc,  # type: ignore[arg-type]
        current,
        "file:///tmp/missing.rs",
        [
            {
                "range": {
                    "start": {"line": 0, "character": 0},
                    "end": {"line": 0, "character": 1},
                },
                "newText": "z",
            }
        ],
        store=store,
    )
    assert len(missing) == 1
    assert missing[0].resolution_status is ResolutionStatus.UNRESOLVED
    assert missing[0].is_applicable(0) is False
