# -*- coding: utf-8 -*-
"""R263: DocumentStore canonical URI identity — aliases share OPEN_BUFFER."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

from core.document_snapshot import DocumentSnapshot
from core.document_store import (
    DocumentSource,
    DocumentStore,
    ResolutionStatus,
    canonicalize_document_uri,
)
from core.symbol_index import SourceSpan
from infrastructure.file_uri import make_workspace_document_loader, path_to_file_uri
from infrastructure.lsp_position_codec import LspPositionCodec
from infrastructure.lsp_semantic import _span_for_uri


def test_canonicalize_collapses_localhost_and_dot_segments(tmp_path: Path) -> None:
    path = tmp_path / "a.py"
    path.write_text("x\n", encoding="utf-8")
    canonical = path_to_file_uri(str(path))
    localhost = f"file://localhost{path.resolve().as_posix()}"
    dotted = path_to_file_uri(str(tmp_path / "." / "a.py"))
    assert canonicalize_document_uri(localhost) == canonical
    assert canonicalize_document_uri(dotted) == canonical
    assert canonicalize_document_uri(canonical) == canonical


def test_canonicalize_percent_encoding_alias(tmp_path: Path) -> None:
    path = tmp_path / "foo bar.py"
    path.write_text("y\n", encoding="utf-8")
    encoded = "file://" + quote(str(path.resolve()))
    assert canonicalize_document_uri(encoded) == path_to_file_uri(str(path))


def test_canonicalize_symlink_collision(tmp_path: Path) -> None:
    real = tmp_path / "real.py"
    real.write_text("z\n", encoding="utf-8")
    link = tmp_path / "link.py"
    os.symlink(real.name, link)
    assert canonicalize_document_uri(path_to_file_uri(str(link))) == path_to_file_uri(str(real))


def test_localhost_alias_does_not_replace_open_buffer(tmp_path: Path) -> None:
    path = tmp_path / "buf.py"
    path.write_text("disk\n", encoding="utf-8")
    canonical = path_to_file_uri(str(path))
    alias = f"file://localhost{path.resolve().as_posix()}"
    store = DocumentStore(loader=make_workspace_document_loader(str(tmp_path)))
    buf = DocumentSnapshot(uri=canonical, text="unsaved\n", version=4, language_id="python")
    store.put_buffer(buf)

    resolved = store.resolve(alias)
    assert resolved is not None
    assert resolved.text == "unsaved\n"
    assert resolved.version == 4
    assert store.get_entry(canonical).source is DocumentSource.OPEN_BUFFER
    assert store.get_entry(alias).source is DocumentSource.OPEN_BUFFER
    assert len(store) == 1


def test_put_disk_refuses_to_clobber_open_buffer(tmp_path: Path) -> None:
    path = tmp_path / "keep.py"
    path.write_text("disk\n", encoding="utf-8")
    uri = path_to_file_uri(str(path))
    store = DocumentStore()
    buf = DocumentSnapshot(uri=uri, text="buffer\n", version=2)
    store.put_buffer(buf)
    store.put_disk(DocumentSnapshot(uri=uri, text="disk\n", version=0))
    assert store.get(uri) is not None
    assert store.get(uri).text == "buffer\n"
    assert store.get_entry(uri).source is DocumentSource.OPEN_BUFFER


def test_percent_alias_resolve_hits_open_buffer(tmp_path: Path) -> None:
    path = tmp_path / "spaced name.py"
    path.write_text("disk\n", encoding="utf-8")
    canonical = path_to_file_uri(str(path))
    encoded = "file://" + quote(str(path.resolve()))
    store = DocumentStore(loader=make_workspace_document_loader(str(tmp_path)))
    store.put_buffer(DocumentSnapshot(uri=canonical, text="live\n", version=1))
    hit = store.resolve(encoded)
    assert hit is not None and hit.text == "live\n"
    assert store.get_entry(encoded).source is DocumentSource.OPEN_BUFFER


def test_span_for_uri_uses_open_buffer_via_localhost_alias(tmp_path: Path) -> None:
    path = tmp_path / "span.py"
    path.write_text("abcdefghij\n", encoding="utf-8")
    canonical = path_to_file_uri(str(path))
    alias = f"file://localhost{path.resolve().as_posix()}"
    store = DocumentStore(loader=make_workspace_document_loader(str(tmp_path)))
    # Unsaved text shorter than disk — wrong decode would use disk offsets.
    buf = DocumentSnapshot(uri=canonical, text="abc\n", version=3, language_id="python")
    store.put_buffer(buf)
    codec = LspPositionCodec()
    proc = SimpleNamespace(codec=codec)
    span, status, target = _span_for_uri(
        proc,  # type: ignore[arg-type]
        buf,
        alias,
        {
            "start": {"line": 0, "character": 0},
            "end": {"line": 0, "character": 3},
        },
        store=store,
    )
    assert status is ResolutionStatus.RESOLVED
    assert target is not None and target.text == "abc\n"
    assert span == SourceSpan(0, 3)
    assert store.get_entry(canonical).source is DocumentSource.OPEN_BUFFER


def test_discard_alias_removes_canonical_entry(tmp_path: Path) -> None:
    path = tmp_path / "gone.py"
    path.write_text("x\n", encoding="utf-8")
    uri = path_to_file_uri(str(path))
    alias = f"file://localhost{path.resolve().as_posix()}"
    store = DocumentStore()
    store.put_buffer(DocumentSnapshot(uri=uri, text="x\n", version=1))
    store.discard(alias)
    assert uri not in store
    assert alias not in store
    assert len(store) == 0
