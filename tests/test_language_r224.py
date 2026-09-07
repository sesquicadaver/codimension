# -*- coding: utf-8 -*-
"""R224: DocumentStore resolves foreign URI spans for LSP locations/edits."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

from core.document_snapshot import DocumentSnapshot, TextEdit
from core.document_store import DocumentStore, ResolutionStatus
from core.semantic import WorkspaceTextEdit
from core.symbol_index import SourceSpan
from infrastructure.file_uri import load_document_from_uri, path_to_file_uri
from infrastructure.lsp_position_codec import LspPositionCodec
from infrastructure.lsp_process import LspProcessRegistry
from infrastructure.lsp_semantic import (
    LspSemanticConfig,
    LspSemanticProvider,
    _parse_locations,
    _parse_text_edits,
)


def test_document_store_resolve_cache_and_loader() -> None:
    loaded: list[str] = []

    def _loader(uri: str) -> DocumentSnapshot | None:
        loaded.append(uri)
        return DocumentSnapshot(uri=uri, text="abc\n", version=0)

    store = DocumentStore(loader=_loader)
    first = store.resolve("mem:a")
    second = store.resolve("mem:a")
    assert first is not None and first.text == "abc\n"
    assert second is first
    assert loaded == ["mem:a"]
    store.put(DocumentSnapshot(uri="mem:b", text="x", version=1))
    assert store.resolve("mem:b") is not None
    assert "mem:b" in store
    store.discard("mem:b")
    assert store.get("mem:b") is None


def test_load_document_from_file_uri(tmp_path: Path) -> None:
    path = tmp_path / "lib.rs"
    path.write_text("fn helper() {}\n", encoding="utf-8")
    uri = path_to_file_uri(str(path))
    snap = load_document_from_uri(uri, language_id="rust")
    assert snap is not None
    assert snap.uri == uri
    assert "helper" in snap.text


def test_parse_locations_foreign_uri_uses_store() -> None:
    from types import SimpleNamespace

    codec = LspPositionCodec()
    current = DocumentSnapshot(uri="file:///tmp/a.rs", text="use crate::b::X;\n", version=1)
    foreign = DocumentSnapshot(uri="file:///tmp/b.rs", text="pub struct X {}\n", version=0)
    store = DocumentStore()
    store.put(foreign)
    proc = SimpleNamespace(codec=codec)

    locs = _parse_locations(
        proc,  # type: ignore[arg-type]
        current,
        {
            "uri": foreign.uri,
            "range": {
                "start": {"line": 0, "character": 11},
                "end": {"line": 0, "character": 12},
            },
        },
        store=store,
    )
    assert len(locs) == 1
    assert locs[0].uri == foreign.uri
    # "X" in "pub struct X {}" starts at offset 11
    assert locs[0].span == SourceSpan(11, 12)
    assert locs[0].span != SourceSpan(0, 0)


def test_parse_locations_foreign_without_store_is_unresolved() -> None:
    from types import SimpleNamespace

    codec = LspPositionCodec()
    current = DocumentSnapshot(uri="file:///tmp/a.rs", text="use x;\n", version=1)
    proc = SimpleNamespace(codec=codec)

    locs = _parse_locations(
        proc,  # type: ignore[arg-type]
        current,
        {
            "uri": "file:///tmp/missing.rs",
            "range": {
                "start": {"line": 2, "character": 4},
                "end": {"line": 2, "character": 8},
            },
        },
        store=DocumentStore(),
    )
    assert locs[0].resolution_status is ResolutionStatus.UNRESOLVED
    assert locs[0].span == SourceSpan(0, 0)
    edit = WorkspaceTextEdit(
        uri=locs[0].uri,
        edit=TextEdit(span=locs[0].span, new_text="x"),
        resolution_status=locs[0].resolution_status,
    )
    assert edit.is_applicable() is False


def test_parse_text_edits_foreign_uri(tmp_path: Path) -> None:
    from types import SimpleNamespace

    codec = LspPositionCodec()
    other = tmp_path / "other.rs"
    other.write_text("fn rename_me() {}\n", encoding="utf-8")
    other_uri = path_to_file_uri(str(other))
    current = DocumentSnapshot(uri="file:///tmp/main.rs", text="rename_me();\n", version=1)
    store = DocumentStore(loader=load_document_from_uri)
    proc = SimpleNamespace(codec=codec)

    edits = _parse_text_edits(
        proc,  # type: ignore[arg-type]
        current,
        other_uri,
        [
            {
                "range": {
                    "start": {"line": 0, "character": 3},
                    "end": {"line": 0, "character": 12},
                },
                "newText": "renamed",
            }
        ],
        store=store,
    )
    assert len(edits) == 1
    assert edits[0].uri == other_uri
    assert edits[0].edit.span == SourceSpan(3, 12)
    assert edits[0].edit.new_text == "renamed"


_FAKE_CROSS_FILE_LSP = textwrap.dedent(
    r"""
    import json
    import sys

    def read_msg():
        headers = {}
        while True:
            line = sys.stdin.buffer.readline()
            if not line:
                return None
            if line in (b"\r\n", b"\n"):
                break
            key, val = line.decode("ascii").split(":", 1)
            headers[key.strip().lower()] = val.strip()
        n = int(headers["content-length"])
        body = sys.stdin.buffer.read(n)
        return json.loads(body.decode("utf-8"))

    def write_msg(obj):
        raw = json.dumps(obj, separators=(",", ":")).encode("utf-8")
        sys.stdout.buffer.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii"))
        sys.stdout.buffer.write(raw)
        sys.stdout.buffer.flush()

    FOREIGN = None
    while True:
        msg = read_msg()
        if msg is None:
            break
        method = msg.get("method")
        mid = msg.get("id")
        params = msg.get("params") or {}
        if method == "exit":
            break
        if method == "textDocument/didOpen":
            # Capture foreign URI from env-like marker in main file text.
            text = ((params.get("textDocument") or {}).get("text") or "")
            for line in text.splitlines():
                if line.startswith("// FOREIGN="):
                    FOREIGN = line.split("=", 1)[1].strip()
            continue
        if method in ("initialized", "$/cancelRequest", "textDocument/didChange", "textDocument/didClose"):
            continue
        if mid is None:
            continue
        if method == "initialize":
            write_msg({
                "jsonrpc": "2.0",
                "id": mid,
                "result": {"capabilities": {}, "serverInfo": {"name": "fake-r224"}},
            })
        elif method == "shutdown":
            write_msg({"jsonrpc": "2.0", "id": mid, "result": None})
        elif method == "textDocument/definition":
            write_msg({
                "jsonrpc": "2.0",
                "id": mid,
                "result": {
                    "uri": FOREIGN,
                    "range": {
                        "start": {"line": 0, "character": 3},
                        "end": {"line": 0, "character": 9},
                    },
                },
            })
        else:
            write_msg({
                "jsonrpc": "2.0",
                "id": mid,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            })
    """
)


def test_provider_definition_cross_file_span(tmp_path: Path) -> None:
    """End-to-end: definition into another file:// loads text and decodes span."""
    script = tmp_path / "fake_lsp_r224.py"
    script.write_text(_FAKE_CROSS_FILE_LSP, encoding="utf-8")
    foreign_path = tmp_path / "lib.rs"
    foreign_path.write_text("fn target() {}\n", encoding="utf-8")
    foreign_uri = path_to_file_uri(str(foreign_path))

    registry = LspProcessRegistry()
    config = LspSemanticConfig(
        language_id="rust",
        workspace_root=str(tmp_path),
        command=(sys.executable, str(script)),
        allowlist=(sys.executable,),
        provider_id="lsp.fake-r224",
    )
    provider = LspSemanticProvider(registry, config)
    doc = DocumentSnapshot(
        uri=path_to_file_uri(str(tmp_path / "main.rs")),
        text=f"// FOREIGN={foreign_uri}\ntarget();\n",
        version=1,
        language_id="rust",
    )
    locs = provider.definition(doc, offset=len(doc.text) - 3)
    assert len(locs) == 1
    assert locs[0].uri == foreign_uri
    assert locs[0].span == SourceSpan(3, 9)
    registry.shutdown_all()
