# -*- coding: utf-8 -*-
"""R244: LSP transport lease — pending+write atomic; stale server msgs isolated."""

from __future__ import annotations

import sys
import textwrap
import time
from concurrent.futures import Future
from pathlib import Path

import pytest
from infrastructure.lsp_process import LspProcess, LspProcessKey, LspProtocolError


class _FakeStdin:
    """Records framed writes for lease/reply targeting tests."""

    def __init__(self) -> None:
        self.chunks: list[bytes] = []

    def write(self, data: bytes) -> int:
        self.chunks.append(data)
        return len(data)

    def flush(self) -> None:
        return None


class _FakeProc:
    """Minimal stand-in for ``subprocess.Popen`` used by lease helpers."""

    def __init__(self, *, dead: bool = False) -> None:
        self.stdin = _FakeStdin()
        self.stdout = None
        self.stderr = None
        self._exit = 1 if dead else None

    def poll(self) -> int | None:
        return self._exit


def _bare_proc() -> LspProcess:
    key = LspProcessKey("rust", "/tmp/r244-unit", "")
    return LspProcess(key, ("/bin/true",), allowlist=("/bin/true",))


def _wait_regs(proc: LspProcess, *, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.dynamic_registrations():
            return True
        time.sleep(0.05)
    return False


def test_bind_pending_and_write_uses_one_lease_generation() -> None:
    """Pending key generation must match the process that receives the frame."""
    proc = _bare_proc()
    fake = _FakeProc()
    proc._proc = fake  # type: ignore[assignment]
    proc._transport_generation = 11
    fut: Future = Future()
    message = {"jsonrpc": "2.0", "id": 9, "method": "textDocument/hover"}
    key = proc._bind_pending_and_write(9, fut, message)
    assert key == (11, 9)
    assert (11, 9) in proc._pending
    assert proc._pending[(11, 9)] is fut
    assert fake.stdin.chunks
    assert b"textDocument/hover" in fake.stdin.chunks[0]


def test_bind_pending_survives_generation_bump_after_lease() -> None:
    """After bind, bumping transport generation must not retarget that pending key."""
    proc = _bare_proc()
    fake = _FakeProc()
    proc._proc = fake  # type: ignore[assignment]
    proc._transport_generation = 3
    fut: Future = Future()
    key = proc._bind_pending_and_write(1, fut, {"jsonrpc": "2.0", "id": 1, "method": "ping"})
    proc._transport_generation = 4
    proc._proc = _FakeProc()  # type: ignore[assignment]
    assert key == (3, 1)
    assert proc._pop_pending(key) is fut
    assert proc._pop_pending((4, 1)) is None


def test_stale_notification_does_not_pollute_live_queue() -> None:
    proc = _bare_proc()
    proc._transport_generation = 5
    old = _FakeProc()
    proc._dispatch(
        {"jsonrpc": "2.0", "method": "window/logMessage", "params": {"type": 1, "message": "old"}},
        generation=4,
        proc=old,  # type: ignore[arg-type]
    )
    assert proc.drain_notifications() == []
    proc._dispatch(
        {"jsonrpc": "2.0", "method": "window/logMessage", "params": {"type": 1, "message": "live"}},
        generation=5,
        proc=old,  # type: ignore[arg-type]
    )
    notes = proc.drain_notifications()
    assert len(notes) == 1
    assert notes[0]["params"]["message"] == "live"


def test_stale_register_capability_skips_side_effects_but_replies_on_reader_proc() -> None:
    """Old reader must not store registrations on the new generation's table."""
    proc = _bare_proc()
    old = _FakeProc()
    live = _FakeProc()
    proc._proc = live  # type: ignore[assignment]
    proc._transport_generation = 2
    proc._dispatch(
        {
            "jsonrpc": "2.0",
            "id": 77,
            "method": "client/registerCapability",
            "params": {
                "registrations": [
                    {"id": "stale-reg", "method": "textDocument/hover"},
                ]
            },
        },
        generation=1,
        proc=old,  # type: ignore[arg-type]
    )
    assert proc.dynamic_registrations() == ()
    assert old.stdin.chunks
    assert b"77" in old.stdin.chunks[0]
    assert live.stdin.chunks == []


def test_live_register_capability_stores_and_replies_on_reader_proc() -> None:
    proc = _bare_proc()
    live = _FakeProc()
    proc._proc = live  # type: ignore[assignment]
    proc._transport_generation = 2
    proc._dispatch(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "client/registerCapability",
            "params": {
                "registrations": [
                    {"id": "live-reg", "method": "textDocument/hover"},
                ]
            },
        },
        generation=2,
        proc=live,  # type: ignore[arg-type]
    )
    regs = proc.dynamic_registrations()
    assert len(regs) == 1
    assert regs[0]["id"] == "live-reg"
    assert live.stdin.chunks


def test_stale_apply_edit_does_not_queue_preview() -> None:
    proc = _bare_proc()
    old = _FakeProc()
    proc._proc = _FakeProc()  # type: ignore[assignment]
    proc._transport_generation = 9
    proc._dispatch(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "workspace/applyEdit",
            "params": {"edit": {"changes": {}}},
        },
        generation=8,
        proc=old,  # type: ignore[arg-type]
    )
    assert proc.drain_apply_edit_previews() == []
    assert old.stdin.chunks  # still refused on the old pipe


def test_write_raises_when_lease_proc_dead() -> None:
    proc = _bare_proc()
    proc._proc = _FakeProc(dead=True)  # type: ignore[assignment]
    proc._transport_generation = 1
    with pytest.raises(LspProtocolError, match="not running"):
        proc._write({"jsonrpc": "2.0", "method": "exit"})


_SERVER_PUSH_LSP = textwrap.dedent(
    r"""
    import json
    import sys
    from pathlib import Path

    control = Path(sys.argv[1])

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

    def gate_set(name):
        return control.exists() and name in control.read_text(encoding="utf-8").splitlines()

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
            write_msg({
                "jsonrpc": "2.0",
                "id": mid,
                "result": {"capabilities": {}, "serverInfo": {"name": "fake-r244"}},
            })
            # Optionally push a registration when the control gate is already set.
            if gate_set("push-register"):
                write_msg({
                    "jsonrpc": "2.0",
                    "id": 9001,
                    "method": "client/registerCapability",
                    "params": {
                        "registrations": [
                            {"id": "from-server", "method": "textDocument/hover"}
                        ]
                    },
                })
        elif method == "shutdown":
            write_msg({"jsonrpc": "2.0", "id": mid, "result": None})
        elif method == "ping":
            write_msg({"jsonrpc": "2.0", "id": mid, "result": {"pong": True}})
        else:
            write_msg({
                "jsonrpc": "2.0",
                "id": mid,
                "error": {"code": -32601, "message": f"unknown {method}"},
            })
    """
)


@pytest.fixture()
def push_lsp(tmp_path: Path) -> tuple[Path, Path]:
    script = tmp_path / "push_lsp.py"
    control = tmp_path / "gates.txt"
    control.write_text("", encoding="utf-8")
    script.write_text(_SERVER_PUSH_LSP, encoding="utf-8")
    return script, control


def test_live_server_register_capability_roundtrip(
    tmp_path: Path, push_lsp: tuple[Path, Path]
) -> None:
    """End-to-end: live-generation registerCapability is stored after reply."""
    script, control = push_lsp
    key = LspProcessKey("rust", str(tmp_path), "")
    proc = LspProcess(
        key,
        (sys.executable, str(script), str(control)),
        allowlist=(sys.executable,),
        backoff_initial=0.01,
        request_timeout=5.0,
    )
    control.write_text("push-register\n", encoding="utf-8")
    proc.ensure_initialized()
    assert _wait_regs(proc)
    regs = proc.dynamic_registrations()
    assert any(r.get("id") == "from-server" for r in regs)
    assert proc.request("ping", {}) == {"pong": True}
    proc.shutdown()


def test_spawn_clears_stale_dynamic_registrations(
    tmp_path: Path, push_lsp: tuple[Path, Path]
) -> None:
    """New transport generation drops capability table from the prior subprocess."""
    script, control = push_lsp
    key = LspProcessKey("rust", str(tmp_path), "")
    proc = LspProcess(
        key,
        (sys.executable, str(script), str(control)),
        allowlist=(sys.executable,),
        backoff_initial=0.01,
        max_restarts=3,
        request_timeout=5.0,
    )
    control.write_text("push-register\n", encoding="utf-8")
    proc.ensure_initialized()
    assert _wait_regs(proc)
    assert proc._proc is not None
    old_gen = proc._transport_generation
    proc._proc.kill()
    proc._proc.wait(timeout=5)
    control.write_text("", encoding="utf-8")  # no push on second handshake
    assert proc.request("ping", {}) == {"pong": True}
    assert proc._transport_generation > old_gen
    assert proc.dynamic_registrations() == ()
    proc.shutdown()
