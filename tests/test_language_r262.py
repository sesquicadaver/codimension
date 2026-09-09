# -*- coding: utf-8 -*-
"""R262: generation-pinned LSP notify — restart mid-sync re-didOpen, not didChange."""

from __future__ import annotations

import json
import sys
import textwrap
import time
from pathlib import Path

import pytest
from core.document_snapshot import DocumentSnapshot
from infrastructure.lsp_process import LspProcess, LspProcessRegistry, LspProtocolError
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
        if method == "initialized":
            log_event("notify", {"method": method, "params": params})
            continue
        if method == "$/cancelRequest":
            continue
        if mid is None:
            continue
        if method == "initialize":
            log_event("request", {"method": method})
            write_msg({
                "jsonrpc": "2.0",
                "id": mid,
                "result": {"capabilities": {}, "serverInfo": {"name": "fake-r262"}},
            })
        elif method == "shutdown":
            write_msg({"jsonrpc": "2.0", "id": mid, "result": None})
        elif method == "textDocument/hover":
            log_event("request", {"method": method, "params": params})
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
        provider_id="lsp.test-r262",
    )
    return LspSemanticProvider(registry, config)


def test_r262_notify_expect_generation_refuses_after_restart(
    tmp_path: Path,
    recording_lsp: tuple[Path, Path],
) -> None:
    """Pinned notify must not write after a silent handshake bump."""
    script, log = recording_lsp
    provider = _provider(tmp_path, script, log)
    doc = DocumentSnapshot(
        uri="file:///tmp/r262-pin.rs",
        text="fn a() {}\n",
        version=1,
        language_id="rust",
    )
    provider.sync_document(doc)
    proc = provider._process()
    gen = proc.generation
    assert proc._proc is not None
    proc._proc.kill()
    proc._proc.wait(timeout=5)

    with pytest.raises(LspProtocolError, match="generation changed"):
        proc.notify(
            "textDocument/didChange",
            {
                "textDocument": {"uri": doc.uri, "version": 2},
                "contentChanges": [{"text": "fn a() { 1 }\n"}],
            },
            expect_generation=gen,
        )
    assert proc.generation > gen
    provider._registry.shutdown_all()


def test_r262_crash_between_attach_and_did_change_reopens(
    tmp_path: Path,
    recording_lsp: tuple[Path, Path],
) -> None:
    """Kill the server after attach while URI is open — new gen must get didOpen first."""
    script, log = recording_lsp
    provider = _provider(tmp_path, script, log)
    doc_v1 = DocumentSnapshot(
        uri="file:///tmp/r262.rs",
        text="fn x() {}\n",
        version=1,
        language_id="rust",
    )
    doc_v2 = DocumentSnapshot(
        uri=doc_v1.uri,
        text="fn x() { 1 }\n",
        version=2,
        language_id="rust",
    )

    assert provider.hover(doc_v1, 0) is not None
    assert doc_v1.uri in provider._opened
    gen_before = provider._server_generation

    log.write_text("", encoding="utf-8")
    orig_attach = LspSemanticProvider._attach_process
    crash_budget = {"left": 1}

    def attach_then_kill(self: LspSemanticProvider) -> LspProcess:
        proc = orig_attach(self)
        if crash_budget["left"] > 0 and doc_v1.uri in self._opened:
            crash_budget["left"] -= 1
            assert proc._proc is not None
            proc._proc.kill()
            proc._proc.wait(timeout=5)
        return proc

    LspSemanticProvider._attach_process = attach_then_kill  # type: ignore[method-assign]
    try:
        info = provider.hover(doc_v2, 0)
    finally:
        LspSemanticProvider._attach_process = orig_attach  # type: ignore[method-assign]

    assert info is not None
    assert info.contents == "ok"
    assert crash_budget["left"] == 0
    assert provider._server_generation > gen_before

    events = _wait_events(log, 3)
    methods = [e["method"] for e in events]
    assert "initialize" in methods
    assert "textDocument/didOpen" in methods
    assert "textDocument/hover" in methods
    # Virgin generation must not see didChange before didOpen.
    assert "textDocument/didChange" not in methods
    init_idx = methods.index("initialize")
    open_idx = methods.index("textDocument/didOpen")
    hover_indices = [i for i, m in enumerate(methods) if m == "textDocument/hover"]
    assert hover_indices
    assert init_idx < open_idx < hover_indices[0]
    open_events = [e for e in events if e.get("method") == "textDocument/didOpen"]
    assert open_events
    assert open_events[0]["params"]["textDocument"]["version"] == 2
    assert open_events[0]["params"]["textDocument"]["text"] == doc_v2.text

    provider._registry.shutdown_all()


def test_r262_sync_document_alone_reopens_after_mid_sync_restart(
    tmp_path: Path,
    recording_lsp: tuple[Path, Path],
) -> None:
    """sync_document (no request) must also clear opens and re-didOpen."""
    script, log = recording_lsp
    provider = _provider(tmp_path, script, log)
    doc_v1 = DocumentSnapshot(
        uri="file:///tmp/r262-sync.rs",
        text="fn z() {}\n",
        version=1,
        language_id="rust",
    )
    doc_v2 = DocumentSnapshot(
        uri=doc_v1.uri,
        text="fn z() { 2 }\n",
        version=2,
        language_id="rust",
    )
    provider.sync_document(doc_v1)
    log.write_text("", encoding="utf-8")

    orig_attach = LspSemanticProvider._attach_process
    crash_budget = {"left": 1}

    def attach_then_kill(self: LspSemanticProvider) -> LspProcess:
        proc = orig_attach(self)
        if crash_budget["left"] > 0 and doc_v1.uri in self._opened:
            crash_budget["left"] -= 1
            assert proc._proc is not None
            proc._proc.kill()
            proc._proc.wait(timeout=5)
        return proc

    LspSemanticProvider._attach_process = attach_then_kill  # type: ignore[method-assign]
    try:
        provider.sync_document(doc_v2)
    finally:
        LspSemanticProvider._attach_process = orig_attach  # type: ignore[method-assign]

    assert crash_budget["left"] == 0
    assert provider._opened.get(doc_v2.uri) == 2
    events = _wait_events(log, 2)
    methods = [e["method"] for e in events]
    assert "initialize" in methods
    assert "textDocument/didOpen" in methods
    assert "textDocument/didChange" not in methods
    provider._registry.shutdown_all()
