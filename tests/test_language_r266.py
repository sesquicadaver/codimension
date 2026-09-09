# -*- coding: utf-8 -*-
"""R266: LSP transport invalidate on reader death; strict non-throwing range decode."""

from __future__ import annotations

import sys
import textwrap
import time
from concurrent.futures import Future
from pathlib import Path

import pytest
from core.document_snapshot import DocumentSnapshot
from core.document_store import ResolutionStatus
from core.symbol_index import SourceSpan
from infrastructure.lsp_position_codec import (
    try_parse_lsp_position,
    try_parse_lsp_range,
)
from infrastructure.lsp_process import LspProcess, LspProcessKey, LspProcessState, LspProtocolError
from infrastructure.lsp_semantic import _span_for_uri

_STDOUT_DIE_LSP = textwrap.dedent(
    r"""
    import json
    import os
    import sys
    from pathlib import Path

    log_path = Path(sys.argv[1])
    die_once = Path(sys.argv[2])

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

    def log_event(payload):
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, separators=(",", ":")) + "\n")
            fh.flush()

    while True:
        msg = read_msg()
        if msg is None:
            break
        method = msg.get("method")
        mid = msg.get("id")
        if method == "exit":
            break
        if method in ("initialized", "$/cancelRequest") or mid is None:
            continue
        if method == "initialize":
            log_event({"kind": "initialize", "id": mid})
            write_msg({
                "jsonrpc": "2.0",
                "id": mid,
                "result": {"capabilities": {}, "serverInfo": {"name": "fake-r266"}},
            })
            # First spawn: hard-exit after the reply so the client reader sees EOF
            # and must invalidate / restart before the next RPC (R266).
            if not die_once.exists():
                die_once.write_text("1", encoding="utf-8")
                os._exit(0)
        elif method == "shutdown":
            write_msg({"jsonrpc": "2.0", "id": mid, "result": None})
        elif method == "ping/echo":
            log_event({"kind": "ping", "id": mid})
            write_msg({"jsonrpc": "2.0", "id": mid, "result": {"ok": True}})
        else:
            write_msg({
                "jsonrpc": "2.0",
                "id": mid,
                "error": {"code": -32601, "message": f"unknown {method}"},
            })
    """
)


class _FakeStdin:
    def write(self, data: bytes) -> int:
        return len(data)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None


class _FakeProc:
    """Alive subprocess stand-in; supports kill/wait for restart paths."""

    def __init__(self) -> None:
        self.stdin = _FakeStdin()
        self.stdout = None
        self.stderr = None
        self._exit: int | None = None
        self.killed = False

    def poll(self) -> int | None:
        return self._exit

    def kill(self) -> None:
        self.killed = True
        self._exit = 1

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        if self._exit is None:
            self._exit = 1
        return self._exit


def _bare_proc() -> LspProcess:
    key = LspProcessKey("rust", "/tmp/r266-unit", "")
    return LspProcess(key, ("/bin/true",), allowlist=("/bin/true",), backoff_initial=0.0)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        "x",
        1,
        {},
        {"line": 0},
        {"line": 0, "character": "0"},
        {"line": -1, "character": 0},
        {"line": 0, "character": -1},
        {"line": True, "character": 0},
        {"line": 0.5, "character": 0},
        {"line": 10_000_001, "character": 0},
    ],
)
def test_try_parse_lsp_position_rejects_malformed(payload: object) -> None:
    assert try_parse_lsp_position(payload) is None


def test_try_parse_lsp_position_accepts_valid() -> None:
    pos = try_parse_lsp_position({"line": 2, "character": 7})
    assert pos is not None
    assert pos.line == 2 and pos.character == 7


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {"start": {"line": 0, "character": 0}},
        {"start": {"line": 0, "character": True}, "end": {"line": 1, "character": 0}},
        {"start": {"line": "0", "character": 0}, "end": {"line": 1, "character": 0}},
    ],
)
def test_try_parse_lsp_range_rejects_malformed(payload: object) -> None:
    assert try_parse_lsp_range(payload) is None


def test_span_for_uri_malformed_range_is_unresolved_not_raise() -> None:
    doc = DocumentSnapshot(uri="file:///tmp/a.py", text="abc\n", version=1, language_id="python")
    proc = _bare_proc()
    span, status, target = _span_for_uri(
        proc,
        doc,
        doc.uri,
        {"start": {"line": 0, "character": True}, "end": {"line": 0, "character": 1}},
        store=None,
    )
    assert span == SourceSpan(0, 0)
    assert status is ResolutionStatus.UNRESOLVED
    assert target is None


def test_broken_transport_forces_restart_while_proc_alive() -> None:
    """Reader death must restart even when poll() still reports alive (R266)."""
    proc = _bare_proc()
    fake = _FakeProc()
    proc._state = LspProcessState.RUNNING
    proc._proc = fake  # type: ignore[assignment]
    proc._transport_generation = 5
    proc._broken_transport_generation = 5
    proc._initialized = True
    starts: list[int] = []

    def _fake_start() -> None:
        starts.append(proc._transport_generation)
        proc._proc = _FakeProc()  # type: ignore[assignment]
        proc._transport_generation = 6
        proc._broken_transport_generation = 0
        proc._state = LspProcessState.RUNNING

    proc._start_unlocked = _fake_start  # type: ignore[method-assign]
    with proc._lifecycle_lock:
        proc._ensure_alive_unlocked()
    assert fake.killed is True
    assert starts == [5]
    assert proc._transport_generation == 6
    assert proc._broken_transport_generation == 0


def test_stderr_loop_uses_leased_proc_not_self_proc() -> None:
    """Superseded stderr worker must drain its lease, not the live ``self._proc``."""
    proc = _bare_proc()
    live = _FakeProc()
    proc._proc = live  # type: ignore[assignment]

    class _ChunkStderr:
        def __init__(self) -> None:
            self._chunks = [b"old\n", b""]

        def read(self, _n: int) -> bytes:
            return self._chunks.pop(0) if self._chunks else b""

    old = _FakeProc()
    old.stderr = _ChunkStderr()  # type: ignore[assignment]
    proc._stderr_loop(old, generation=1)  # type: ignore[arg-type]
    assert b"old\n" in b"".join(proc._stderr_chunks)


def test_reader_stdout_death_then_next_rpc_restarts(tmp_path: Path) -> None:
    """After reader EOF invalidates transport, the next RPC must restart (not hang)."""
    script = tmp_path / "stdout_die_lsp.py"
    log = tmp_path / "events.jsonl"
    die_once = tmp_path / "die_once"
    log.write_text("", encoding="utf-8")
    script.write_text(_STDOUT_DIE_LSP, encoding="utf-8")
    key = LspProcessKey("rust", str(tmp_path), "")
    lsp = LspProcess(
        key,
        (sys.executable, str(script), str(log), str(die_once)),
        allowlist=(sys.executable,),
        backoff_initial=0.01,
        request_timeout=5.0,
        max_restarts=3,
    )
    try:
        gen1 = lsp.ensure_initialized(root_uri=tmp_path.as_uri())
        assert gen1 >= 1
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if die_once.exists() and (
                not lsp.initialized
                or lsp._broken_transport_generation == lsp._transport_generation
                or (lsp._proc is not None and lsp._proc.poll() is not None)
            ):
                break
            time.sleep(0.02)
        assert die_once.exists()
        gen2 = lsp.ensure_initialized(root_uri=tmp_path.as_uri())
        assert gen2 > gen1
        result = lsp.request("ping/echo", {})
        assert result == {"ok": True}
    finally:
        lsp.shutdown()


def test_invalidate_fails_pending_for_that_generation_only() -> None:
    proc = _bare_proc()
    doomed: Future = Future()
    survivor: Future = Future()
    with proc._pending_lock:
        proc._pending[(3, 1)] = doomed
        proc._pending[(4, 2)] = survivor
    fake = _FakeProc()
    proc._proc = fake  # type: ignore[assignment]
    proc._transport_generation = 3
    proc._invalidate_transport(fake, 3, "language server stdout closed")  # type: ignore[arg-type]
    assert doomed.done()
    assert isinstance(doomed.exception(), LspProtocolError)
    assert survivor.done() is False
    assert proc._broken_transport_generation == 3
    assert fake.killed is True
