# -*- coding: utf-8 -*-
"""R233: LSP generation-safe lifecycle — crash restart must handshake before requests."""

from __future__ import annotations

import json
import sys
import textwrap
import time
from pathlib import Path

import pytest
from core.document_snapshot import DocumentSnapshot
from infrastructure.lsp_process import LspProcess, LspProcessKey, LspProcessRegistry
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
                "result": {"capabilities": {}, "serverInfo": {"name": "fake-r233"}},
            })
        elif method == "shutdown":
            write_msg({"jsonrpc": "2.0", "id": mid, "result": None})
        elif method == "textDocument/hover":
            log_event("request", {"method": method})
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
        provider_id="lsp.test-r233",
    )
    return LspSemanticProvider(registry, config)


def test_ensure_initialized_bumps_generation(tmp_path: Path, recording_lsp: tuple[Path, Path]) -> None:
    script, log = recording_lsp
    key = LspProcessKey("rust", str(tmp_path), "")
    proc = LspProcess(
        key,
        (sys.executable, str(script), str(log)),
        allowlist=(sys.executable,),
        backoff_initial=0.01,
    )
    assert proc.generation == 0
    gen1 = proc.ensure_initialized()
    assert gen1 == 1
    assert proc.initialized
    assert proc.ensure_initialized() == 1  # idempotent
    proc.shutdown()


def test_crash_with_stale_initialized_flag_rehandshakes(tmp_path: Path, recording_lsp: tuple[Path, Path]) -> None:
    """Production bug: process dies while ``_initialized`` remains True.

    Must restart + initialize before any didOpen / hover (do not clear the flag
    manually — that masked the defect in the R209 test).
    """
    script, log = recording_lsp
    provider = _provider(tmp_path, script, log)
    doc = DocumentSnapshot(uri="file:///tmp/r233.rs", text="fn x() {}\n", version=1, language_id="rust")
    provider.hover(doc, 0)
    events = _wait_events(log, 3)  # initialize + initialized + didOpen (+ hover request)
    methods = [e["method"] for e in events]
    assert methods.count("initialize") >= 1
    assert "textDocument/didOpen" in methods

    proc = provider._process()
    gen_before = proc.generation
    assert proc._proc is not None
    proc._proc.kill()
    proc._proc.wait(timeout=5)
    # Leave ``_initialized`` True — the real crash residue.
    assert proc._initialized is True

    log.write_text("", encoding="utf-8")  # focus on post-crash traffic
    provider.hover(doc, 0)
    events = _wait_events(log, 3)
    methods = [e["method"] for e in events]
    # Handshake must precede document traffic on the new process.
    assert "initialize" in methods
    init_idx = methods.index("initialize")
    open_idx = methods.index("textDocument/didOpen")
    assert init_idx < open_idx
    assert proc.generation > gen_before
    assert provider._server_generation == proc.generation
    provider._registry.shutdown_all()


def test_request_after_crash_does_not_skip_initialize(tmp_path: Path, recording_lsp: tuple[Path, Path]) -> None:
    script, log = recording_lsp
    key = LspProcessKey("rust", str(tmp_path), "")
    proc = LspProcess(
        key,
        (sys.executable, str(script), str(log)),
        allowlist=(sys.executable,),
        backoff_initial=0.01,
        max_restarts=3,
    )
    proc.ensure_initialized()
    assert proc._proc is not None
    proc._proc.kill()
    proc._proc.wait(timeout=5)
    assert proc._initialized is True

    log.write_text("", encoding="utf-8")
    # Direct request path (no provider) must still handshake first.
    proc.request(
        "textDocument/hover",
        {"textDocument": {"uri": "file:///tmp/z.rs"}, "position": {"line": 0, "character": 0}},
    )
    events = _wait_events(log, 2)
    methods = [e["method"] for e in events]
    assert methods[0] == "initialize"
    assert "textDocument/hover" in methods
    proc.shutdown()
