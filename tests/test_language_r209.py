# -*- coding: utf-8 -*-
"""R209: LSP document lifecycle — didChange / didClose / restart re-open."""

from __future__ import annotations

import json
import sys
import textwrap
import time
from pathlib import Path

import pytest
from core.document_snapshot import DocumentSnapshot
from infrastructure.lsp_process import LspProcessRegistry
from infrastructure.lsp_semantic import LspSemanticConfig, LspSemanticProvider

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
        if method == "initialized" or method == "$/cancelRequest":
            continue
        if mid is None:
            continue
        if method == "initialize":
            write_msg({
                "jsonrpc": "2.0",
                "id": mid,
                "result": {"capabilities": {}, "serverInfo": {"name": "fake-lifecycle"}},
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


@pytest.fixture()
def recording_lsp(tmp_path: Path) -> tuple[Path, Path]:
    script = tmp_path / "recording_lsp.py"
    log = tmp_path / "lsp_events.jsonl"
    log.write_text("", encoding="utf-8")
    script.write_text(_RECORDING_LSP, encoding="utf-8")
    return script, log


def _read_events(log: Path) -> list[dict]:
    lines = [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return [json.loads(ln) for ln in lines]


def _wait_events(log: Path, count: int, *, timeout: float = 5.0) -> list[dict]:
    """Poll JSONL until ``count`` notifies are visible (did* are fire-and-forget)."""
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
        language_id="rust",
        workspace_root=str(tmp_path),
        command=(sys.executable, str(script), str(log)),
        allowlist=(sys.executable,),
        provider_id="lsp.test-lifecycle",
    )
    return LspSemanticProvider(registry, config)


def test_did_open_then_did_change_on_version_bump(tmp_path: Path, recording_lsp: tuple[Path, Path]) -> None:
    script, log = recording_lsp
    provider = _provider(tmp_path, script, log)
    doc = DocumentSnapshot(uri="file:///tmp/a.rs", text="fn a() {}\n", version=1, language_id="rust")
    provider.sync_document(doc)
    events = _wait_events(log, 1)
    assert [e["method"] for e in events] == ["textDocument/didOpen"]
    assert events[0]["params"]["textDocument"]["version"] == 1

    updated = doc.with_text("fn a() { 1 }\n", bump_version=True)
    assert updated.version == 2
    provider.sync_document(updated)
    events = _wait_events(log, 2)
    assert [e["method"] for e in events] == ["textDocument/didOpen", "textDocument/didChange"]
    change = events[1]["params"]
    assert change["textDocument"]["version"] == 2
    assert change["contentChanges"] == [{"text": updated.text}]

    # Same version → no extra notify
    provider.sync_document(updated)
    time.sleep(0.05)
    assert len(_read_events(log)) == 2
    provider._registry.shutdown_all()


def test_did_close_drops_tracking(tmp_path: Path, recording_lsp: tuple[Path, Path]) -> None:
    script, log = recording_lsp
    provider = _provider(tmp_path, script, log)
    doc = DocumentSnapshot(uri="file:///tmp/b.rs", text="fn b() {}\n", version=0, language_id="rust")
    provider.sync_document(doc)
    _wait_events(log, 1)
    provider.close_document(doc)
    events = _wait_events(log, 2)
    assert [e["method"] for e in events] == ["textDocument/didOpen", "textDocument/didClose"]
    assert doc.uri not in provider._opened

    # Re-open after close uses didOpen again
    provider.sync_document(doc)
    events = _wait_events(log, 3)
    assert [e["method"] for e in events][-1] == "textDocument/didOpen"
    provider._registry.shutdown_all()


def test_restart_clears_opened_and_reopens(tmp_path: Path, recording_lsp: tuple[Path, Path]) -> None:
    script, log = recording_lsp
    provider = _provider(tmp_path, script, log)
    doc = DocumentSnapshot(uri="file:///tmp/c.rs", text="fn c() {}\n", version=3, language_id="rust")
    provider.hover(doc, 0)
    assert _wait_events(log, 1)[0]["method"] == "textDocument/didOpen"

    # Simulate language-server death: kill the process and mark uninitialized.
    proc = provider._process()
    assert proc._proc is not None
    proc._proc.kill()
    proc._proc.wait(timeout=5)
    proc._initialized = False

    provider.hover(doc, 0)
    methods = [e["method"] for e in _wait_events(log, 2)]
    assert methods.count("textDocument/didOpen") >= 2
    provider._registry.shutdown_all()
