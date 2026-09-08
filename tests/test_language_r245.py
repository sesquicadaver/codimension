# -*- coding: utf-8 -*-
"""R245: editor-owned document versions + Save As URI migrate."""

from __future__ import annotations

import json
import sys
import textwrap
import time
from pathlib import Path

from app.language_services import LanguageServiceManager
from core.document_snapshot import DocumentSnapshot
from core.document_store import DocumentStore
from core.feature_flags import FLAG_LANGUAGE_SERVICES, FeatureFlagsStore
from infrastructure.file_uri import path_to_file_uri
from infrastructure.lsp_process import LspProcessRegistry
from infrastructure.lsp_semantic import LspSemanticConfig, LspSemanticProvider
from ui.language_controller import LanguageController


def test_current_snapshot_never_regresses_store_version(tmp_path: Path) -> None:
    store = FeatureFlagsStore(str(tmp_path / "flags.json"))
    store.set_enabled(FLAG_LANGUAGE_SERVICES, True)
    mgr = LanguageServiceManager()
    assert mgr.attach_workspace(str(tmp_path), store=store, environ={}) is True
    ctrl = LanguageController(mgr)
    path = tmp_path / "buf.py"
    path.write_text("x = 1\n", encoding="utf-8")
    uri = path_to_file_uri(str(path))

    opened = ctrl.snapshot_for_buffer(path=str(path), text="x = 1\n", version=0)
    assert opened is not None
    ctrl.notify_buffer_opened(opened)
    changed = ctrl.snapshot_for_buffer(path=str(path), text="x = 2\n", version=None)
    assert changed is not None and changed.version == 1
    ctrl.notify_buffer_changed(changed)
    assert mgr.document_store.get(uri).version == 1

    # Query-style snapshot must keep version 1 (never force 0).
    query = ctrl.current_snapshot_for_buffer(path=str(path), text="x = 2\n")
    assert query is not None
    assert query.version == 1
    ctrl.notify_buffer_changed(query)
    assert mgr.document_store.get(uri).version == 1

    again = ctrl.snapshot_for_buffer(path=str(path), text="x = 2\n", version=1)
    assert again is not None and again.version == 1
    mgr.shutdown()


def test_migrate_buffer_closes_old_opens_new(tmp_path: Path) -> None:
    store = FeatureFlagsStore(str(tmp_path / "flags.json"))
    store.set_enabled(FLAG_LANGUAGE_SERVICES, True)
    mgr = LanguageServiceManager()
    assert mgr.attach_workspace(str(tmp_path), store=store, environ={}) is True
    assert isinstance(mgr.document_store, DocumentStore)
    ctrl = LanguageController(mgr)
    old_path = tmp_path / "old.py"
    new_path = tmp_path / "new.py"
    old_path.write_text("a = 1\n", encoding="utf-8")
    new_path.write_text("a = 1\n", encoding="utf-8")
    old_uri = path_to_file_uri(str(old_path))
    new_uri = path_to_file_uri(str(new_path))

    opened = ctrl.snapshot_for_buffer(path=str(old_path), text="a = 1\n", version=0)
    assert opened is not None
    ctrl.notify_buffer_opened(opened)
    bumped = ctrl.snapshot_for_buffer(path=str(old_path), text="a = 2\n", version=None)
    assert bumped is not None
    ctrl.notify_buffer_changed(bumped)
    assert mgr.document_store.get(old_uri) is not None

    migrated = DocumentSnapshot(uri=new_uri, text="a = 2\n", version=0, language_id="python")
    ctrl.migrate_buffer(old_uri=old_uri, document=migrated)
    assert mgr.document_store.get(old_uri) is None
    assert mgr.document_store.get(new_uri) is not None
    assert mgr.document_store.get(new_uri).version == 0
    assert mgr.document_store.get(new_uri).text == "a = 2\n"
    mgr.shutdown()


_RECORDING_LSP = textwrap.dedent(
    r"""
    import json
    import sys
    from pathlib import Path

    log_path = Path(sys.argv[1])

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

    def log_event(kind, payload):
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"kind": kind, **payload}, separators=(",", ":")) + "\n")
            fh.flush()

    while True:
        msg = read_msg()
        if msg is None:
            break
        method = msg.get("method")
        mid = msg.get("id")
        params = msg.get("params") or {}
        if method == "exit":
            break
        if method in ("textDocument/didOpen", "textDocument/didChange", "textDocument/didClose"):
            log_event("notify", {"method": method, "params": params})
            continue
        if method in ("initialized", "$/cancelRequest") or mid is None:
            continue
        if method == "initialize":
            write_msg({
                "jsonrpc": "2.0",
                "id": mid,
                "result": {"capabilities": {}, "serverInfo": {"name": "fake-r245"}},
            })
        elif method == "shutdown":
            write_msg({"jsonrpc": "2.0", "id": mid, "result": None})
        elif method == "textDocument/hover":
            write_msg({
                "jsonrpc": "2.0",
                "id": mid,
                "result": {"contents": {"kind": "plaintext", "value": "ok"}},
            })
        else:
            write_msg({
                "jsonrpc": "2.0",
                "id": mid,
                "error": {"code": -32601, "message": f"unknown {method}"},
            })
    """
)


def _read_events(log: Path) -> list[dict]:
    lines = [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return [json.loads(ln) for ln in lines]


def _wait_events(log: Path, count: int, *, timeout: float = 5.0) -> list[dict]:
    deadline = time.monotonic() + timeout
    events: list[dict] = []
    while time.monotonic() < deadline:
        events = _read_events(log)
        if len(events) >= count:
            return events
        time.sleep(0.02)
    return events


def _provider(tmp_path: Path, script: Path, log: Path) -> LspSemanticProvider:
    registry = LspProcessRegistry()
    config = LspSemanticConfig(
        language_id="python",
        workspace_root=str(tmp_path),
        command=(sys.executable, str(script), str(log)),
        allowlist=(sys.executable,),
        provider_id="lsp.test-r245",
    )
    return LspSemanticProvider(registry, config)


def test_lsp_ensure_open_remigrates_on_version_regression(tmp_path: Path) -> None:
    """Regressive snapshot must didClose+didOpen, never didChange to a lower version."""
    script = tmp_path / "recording_lsp.py"
    log = tmp_path / "events.jsonl"
    log.write_text("", encoding="utf-8")
    script.write_text(_RECORDING_LSP, encoding="utf-8")
    provider = _provider(tmp_path, script, log)
    uri = path_to_file_uri(str(tmp_path / "m.py"))
    doc1 = DocumentSnapshot(uri=uri, text="x=1\n", version=0, language_id="python")
    doc2 = DocumentSnapshot(uri=uri, text="x=2\n", version=2, language_id="python")
    doc_regress = DocumentSnapshot(uri=uri, text="x=0\n", version=0, language_id="python")

    provider.sync_document(doc1)
    provider.sync_document(doc2)
    provider.hover(doc_regress, 0)

    events = _wait_events(log, 4)
    methods = [e.get("method") for e in events if e.get("kind") == "notify"]
    assert methods.count("textDocument/didOpen") >= 2
    assert "textDocument/didClose" in methods
    change_versions = [
        (e.get("params") or {}).get("textDocument", {}).get("version")
        for e in events
        if e.get("kind") == "notify" and e.get("method") == "textDocument/didChange"
    ]
    assert 0 not in change_versions
    provider._process().shutdown()


def test_lsp_migrate_close_old_open_new(tmp_path: Path) -> None:
    script = tmp_path / "recording_lsp.py"
    log = tmp_path / "events.jsonl"
    log.write_text("", encoding="utf-8")
    script.write_text(_RECORDING_LSP, encoding="utf-8")
    provider = _provider(tmp_path, script, log)
    old_uri = path_to_file_uri(str(tmp_path / "old.py"))
    new_uri = path_to_file_uri(str(tmp_path / "new.py"))
    old_doc = DocumentSnapshot(uri=old_uri, text="a=1\n", version=1, language_id="python")
    new_doc = DocumentSnapshot(uri=new_uri, text="a=1\n", version=0, language_id="python")
    provider.sync_document(old_doc)
    provider.close_document(old_doc)
    provider.sync_document(new_doc)

    events = _wait_events(log, 3)
    closes = [e for e in events if e.get("method") == "textDocument/didClose"]
    opens = [e for e in events if e.get("method") == "textDocument/didOpen"]
    assert any((e.get("params") or {}).get("textDocument", {}).get("uri") == old_uri for e in closes)
    assert any((e.get("params") or {}).get("textDocument", {}).get("uri") == new_uri for e in opens)
    provider._process().shutdown()
