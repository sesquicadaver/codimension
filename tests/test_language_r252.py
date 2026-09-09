# -*- coding: utf-8 -*-
"""R252: application RPC requires an initialized transport lease."""

from __future__ import annotations

import sys
import textwrap
import threading
import time
from concurrent.futures import Future
from pathlib import Path

import pytest
from infrastructure.lsp_process import LspProcess, LspProcessKey, LspProtocolError


class _FakeStdin:
    def __init__(self) -> None:
        self.chunks: list[bytes] = []

    def write(self, data: bytes) -> int:
        self.chunks.append(data)
        return len(data)

    def flush(self) -> None:
        return None


class _FakeProc:
    def __init__(self) -> None:
        self.stdin = _FakeStdin()
        self.stdout = None
        self.stderr = None

    def poll(self) -> int | None:
        return None


def _bare_proc() -> LspProcess:
    key = LspProcessKey("rust", "/tmp/r252-unit", "")
    return LspProcess(key, ("/bin/true",), allowlist=("/bin/true",))


def test_r252_bind_requires_initialized_for_app_rpc() -> None:
    proc = _bare_proc()
    proc._proc = _FakeProc()  # type: ignore[assignment]
    proc._transport_generation = 3
    proc._initialized = False
    proc._generation = 0
    fut: Future = Future()
    with pytest.raises(LspProtocolError, match="not initialized"):
        proc._bind_pending_and_write(
            1,
            fut,
            {"jsonrpc": "2.0", "id": 1, "method": "textDocument/hover"},
            require_initialized=True,
        )
    assert proc._pending == {}


def test_r252_bind_allows_handshake_without_initialized() -> None:
    proc = _bare_proc()
    fake = _FakeProc()
    proc._proc = fake  # type: ignore[assignment]
    proc._transport_generation = 2
    proc._initialized = False
    fut: Future = Future()
    key = proc._bind_pending_and_write(
        7,
        fut,
        {"jsonrpc": "2.0", "id": 7, "method": "initialize"},
        require_initialized=False,
    )
    assert key == (2, 7)
    assert fake.stdin.chunks
    assert b"initialize" in fake.stdin.chunks[0]


def test_r252_lease_carries_initialized_generation() -> None:
    proc = _bare_proc()
    proc._proc = _FakeProc()  # type: ignore[assignment]
    proc._transport_generation = 5
    proc._initialized = True
    proc._generation = 9
    with proc._write_lock:
        lease = proc._lease_unlocked(require_initialized=True)
    assert lease.generation == 5
    assert lease.initialized_generation == 9


def test_r252_request_binds_while_holding_lifecycle_lock(
    tmp_path: Path,
) -> None:
    """App bind/write must run under lifecycle_lock (handshake barrier)."""
    script = tmp_path / "echo_lsp.py"
    script.write_text(
        textwrap.dedent(
            r"""
            import json, sys
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
                return json.loads(sys.stdin.buffer.read(n).decode("utf-8"))
            def write_msg(obj):
                raw = json.dumps(obj, separators=(",", ":")).encode("utf-8")
                sys.stdout.buffer.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii"))
                sys.stdout.buffer.write(raw)
                sys.stdout.buffer.flush()
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
                    write_msg({"jsonrpc": "2.0", "id": mid, "result": {"capabilities": {}}})
                elif method == "shutdown":
                    write_msg({"jsonrpc": "2.0", "id": mid, "result": None})
                elif method == "ping":
                    write_msg({"jsonrpc": "2.0", "id": mid, "result": {"pong": True}})
                else:
                    write_msg({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": method}})
            """
        ),
        encoding="utf-8",
    )
    key = LspProcessKey("rust", str(tmp_path), "")
    proc = LspProcess(
        key,
        (sys.executable, str(script)),
        allowlist=(sys.executable,),
        backoff_initial=0.01,
        request_timeout=5.0,
    )
    seen: list[bool] = []
    orig = proc._bind_pending_and_write

    def wrapped(*args, **kwargs):
        message = args[2] if len(args) > 2 else kwargs.get("message", {})
        method = message.get("method") if isinstance(message, dict) else None
        if method == "ping":
            seen.append(proc._lifecycle_lock.locked())
            assert proc._initialized is True
            assert kwargs.get("require_initialized") is True
        return orig(*args, **kwargs)

    proc._bind_pending_and_write = wrapped  # type: ignore[method-assign]
    try:
        assert proc.request("ping", {}) == {"pong": True}
        assert seen == [True]
    finally:
        proc.shutdown()


def test_r252_mid_handshake_blocks_concurrent_app_bind() -> None:
    """While handshake holds lifecycle_lock, app bind with require_initialized fails."""
    proc = _bare_proc()
    proc._proc = _FakeProc()  # type: ignore[assignment]
    proc._transport_generation = 1
    proc._initialized = False
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def handshake_holder() -> None:
        with proc._lifecycle_lock:
            barrier.wait(timeout=5)
            time.sleep(0.2)

    def app_writer() -> None:
        barrier.wait(timeout=5)
        try:
            proc._bind_pending_and_write(
                3,
                Future(),
                {"jsonrpc": "2.0", "id": 3, "method": "ping"},
                require_initialized=True,
            )
        except BaseException as exc:  # noqa: BLE001 — capture for assertion
            errors.append(exc)

    t1 = threading.Thread(target=handshake_holder)
    t2 = threading.Thread(target=app_writer)
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)
    assert len(errors) == 1
    assert isinstance(errors[0], LspProtocolError)
    assert "not initialized" in str(errors[0])
