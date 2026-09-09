# -*- coding: utf-8 -*-
"""R253: didOpen/didChange + semantic request share one LSP generation."""

from __future__ import annotations

import json
import sys
import textwrap
import time
from pathlib import Path

import pytest
from core.document_snapshot import DocumentSnapshot
from infrastructure.lsp_process import LspProcess, LspProcessRegistry
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
                "result": {"capabilities": {}, "serverInfo": {"name": "fake-r253"}},
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
        elif method == "textDocument/definition":
            log_event("request", {"method": method, "params": params})
            write_msg({
                "jsonrpc": "2.0",
                "id": mid,
                "result": [{
                    "uri": params.get("textDocument", {}).get("uri", ""),
                    "range": {
                        "start": {"line": 0, "character": 0},
                        "end": {"line": 0, "character": 1},
                    },
                }],
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
        provider_id="lsp.test-r253",
    )
    return LspSemanticProvider(registry, config)


def test_r253_resync_when_request_restarts_after_did_open(
    tmp_path: Path,
    recording_lsp: tuple[Path, Path],
) -> None:
    """Kill the server after sync so request() re-handshakes without didOpen — must retry."""
    script, log = recording_lsp
    provider = _provider(tmp_path, script, log)
    doc = DocumentSnapshot(
        uri="file:///tmp/r253.rs",
        text="fn x() {}\n",
        version=1,
        language_id="rust",
    )

    # Warm up once so the process exists.
    assert provider.hover(doc, 0) is not None
    proc = provider._process()
    gen_before = proc.generation

    log.write_text("", encoding="utf-8")
    crash_budget = {"left": 1}
    orig_request = LspProcess.request

    def crashing_request(self: LspProcess, method: str, params=None, *, timeout=None, expect_generation=None):
        if method == "textDocument/hover" and crash_budget["left"] > 0:
            crash_budget["left"] -= 1
            assert self._proc is not None
            self._proc.kill()
            self._proc.wait(timeout=5)
            # Leave initialized residue so ensure_alive must restart+handshake.
            assert self._initialized is True
        return orig_request(
            self,
            method,
            params,
            timeout=timeout,
            expect_generation=expect_generation,
        )

    LspProcess.request = crashing_request  # type: ignore[method-assign]
    try:
        info = provider.hover(doc, 0)
    finally:
        LspProcess.request = orig_request  # type: ignore[method-assign]

    assert info is not None
    assert info.contents == "ok"
    assert crash_budget["left"] == 0
    assert proc.generation > gen_before

    events = _wait_events(log, 3)
    methods = [e["method"] for e in events]
    assert "initialize" in methods
    assert "textDocument/didOpen" in methods
    assert "textDocument/hover" in methods
    # No semantic request may precede didOpen on the post-crash generation.
    init_idx = methods.index("initialize")
    open_idx = methods.index("textDocument/didOpen")
    hover_indices = [i for i, m in enumerate(methods) if m == "textDocument/hover"]
    assert hover_indices
    assert init_idx < open_idx < hover_indices[0]
    assert methods.count("textDocument/hover") == 1

    provider._registry.shutdown_all()


def test_r253_definition_also_generation_atomic(
    tmp_path: Path,
    recording_lsp: tuple[Path, Path],
) -> None:
    script, log = recording_lsp
    provider = _provider(tmp_path, script, log)
    doc = DocumentSnapshot(
        uri="file:///tmp/r253-def.rs",
        text="fn y() {}\n",
        version=1,
        language_id="rust",
    )
    assert provider.definition(doc, 0)  # warm
    log.write_text("", encoding="utf-8")

    crash_budget = {"left": 1}
    orig_request = LspProcess.request

    def crashing_request(self: LspProcess, method: str, params=None, *, timeout=None, expect_generation=None):
        if method == "textDocument/definition" and crash_budget["left"] > 0:
            crash_budget["left"] -= 1
            assert self._proc is not None
            self._proc.kill()
            self._proc.wait(timeout=5)
        return orig_request(
            self,
            method,
            params,
            timeout=timeout,
            expect_generation=expect_generation,
        )

    LspProcess.request = crashing_request  # type: ignore[method-assign]
    try:
        locs = provider.definition(doc, 0)
    finally:
        LspProcess.request = orig_request  # type: ignore[method-assign]

    assert len(locs) == 1
    events = _wait_events(log, 3)
    methods = [e["method"] for e in events]
    init_idx = methods.index("initialize")
    open_idx = methods.index("textDocument/didOpen")
    def_indices = [i for i, m in enumerate(methods) if m == "textDocument/definition"]
    assert methods.count("textDocument/definition") == 1
    assert init_idx < open_idx < def_indices[0]
    provider._registry.shutdown_all()
