# -*- coding: utf-8 -*-
"""R234: LSP pending synchronization — lock, generation keys, race ownership."""

from __future__ import annotations

import sys
import textwrap
import threading
import time
from concurrent.futures import Future
from pathlib import Path

import pytest
from infrastructure.lsp_process import LspProcess, LspProcessKey, LspProtocolError

_CONTROLLABLE_LSP = textwrap.dedent(
    r"""
    import json
    import sys
    import time
    from pathlib import Path

    control = Path(sys.argv[1])
    log_path = Path(sys.argv[2])

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

    def wait_gate(name, timeout=10.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if control.exists() and name in control.read_text(encoding="utf-8").splitlines():
                return True
            time.sleep(0.01)
        return False

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
            log_event({"kind": "request", "method": method, "id": mid})
            write_msg({
                "jsonrpc": "2.0",
                "id": mid,
                "result": {"capabilities": {}, "serverInfo": {"name": "fake-r234"}},
            })
        elif method == "shutdown":
            write_msg({"jsonrpc": "2.0", "id": mid, "result": None})
        elif method == "slow/echo":
            log_event({"kind": "request", "method": method, "id": mid})
            wait_gate("release-echo")
            write_msg({"jsonrpc": "2.0", "id": mid, "result": {"ok": True, "id": mid}})
        else:
            write_msg({
                "jsonrpc": "2.0",
                "id": mid,
                "error": {"code": -32601, "message": f"unknown {method}"},
            })
    """
)


@pytest.fixture()
def controllable_lsp(tmp_path: Path) -> tuple[Path, Path, Path]:
    script = tmp_path / "controllable_lsp.py"
    control = tmp_path / "gates.txt"
    log = tmp_path / "events.jsonl"
    control.write_text("", encoding="utf-8")
    log.write_text("", encoding="utf-8")
    script.write_text(_CONTROLLABLE_LSP, encoding="utf-8")
    return script, control, log


def _proc(tmp_path: Path, script: Path, control: Path, log: Path, **kwargs) -> LspProcess:
    key = LspProcessKey("rust", str(tmp_path), "")
    return LspProcess(
        key,
        (sys.executable, str(script), str(control), str(log)),
        allowlist=(sys.executable,),
        backoff_initial=0.01,
        request_timeout=kwargs.pop("request_timeout", 30.0),
        **kwargs,
    )


def test_put_pop_pending_is_generation_scoped() -> None:
    """Pending keys include transport generation; pop transfers ownership."""
    key = LspProcessKey("rust", "/tmp/r234-unit", "")
    proc = LspProcess(key, ("/bin/true",), allowlist=("/bin/true",))
    proc._transport_generation = 7
    fut: Future = Future()
    pending_key = proc._put_pending(42, fut)
    assert pending_key == (7, 42)
    assert proc._pop_pending(pending_key) is fut
    assert proc._pop_pending(pending_key) is None


def test_settle_future_ignores_double_complete() -> None:
    fut: Future = Future()
    LspProcess._settle_future(fut, result=1)
    LspProcess._settle_future(fut, result=2)
    LspProcess._settle_future(fut, exception=RuntimeError("x"))
    assert fut.result() == 1


def test_fail_pending_only_touches_own_generation() -> None:
    """Old-reader EOF must not fail futures registered for a newer spawn."""
    key = LspProcessKey("rust", "/tmp/r234-fail", "")
    proc = LspProcess(key, ("/bin/true",), allowlist=("/bin/true",))
    doomed: Future = Future()
    survivor: Future = Future()
    with proc._pending_lock:
        proc._pending[(3, 1)] = doomed
        proc._pending[(4, 2)] = survivor
    proc._fail_pending("old reader eof", generation=3)
    assert doomed.done()
    assert isinstance(doomed.exception(), LspProtocolError)
    assert survivor.done() is False
    with proc._pending_lock:
        assert (4, 2) in proc._pending
        assert (3, 1) not in proc._pending


def test_response_vs_timeout_race(tmp_path: Path, controllable_lsp: tuple[Path, Path, Path]) -> None:
    """Barrier: response and timeout both contend to settle the same Future."""
    script, control, log = controllable_lsp
    proc = _proc(tmp_path, script, control, log, request_timeout=0.2)
    proc.ensure_initialized()

    errors: list[BaseException] = []
    results: list[object] = []
    barrier = threading.Barrier(2, timeout=5)

    def caller() -> None:
        barrier.wait()
        try:
            results.append(proc.request("slow/echo", {}))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    def releaser() -> None:
        barrier.wait()
        time.sleep(0.05)
        control.write_text("release-echo\n", encoding="utf-8")

    t1 = threading.Thread(target=caller)
    t2 = threading.Thread(target=releaser)
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)
    assert t1.is_alive() is False
    assert proc._reader is not None
    assert proc._reader.is_alive()
    assert results or errors
    assert all(isinstance(exc, LspProtocolError) for exc in errors)
    proc.shutdown()


def test_response_vs_shutdown_race(tmp_path: Path, controllable_lsp: tuple[Path, Path, Path]) -> None:
    script, control, log = controllable_lsp
    proc = _proc(tmp_path, script, control, log)
    proc.ensure_initialized()

    started = threading.Event()
    errors: list[BaseException] = []

    def caller() -> None:
        started.set()
        try:
            proc.request("slow/echo", {}, timeout=5.0)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    t = threading.Thread(target=caller)
    t.start()
    assert started.wait(5)
    time.sleep(0.05)
    # Fake server is blocked on slow/echo, so LSP shutdown RPC will time out —
    # keep the wait short; terminate path must still settle the in-flight request.
    proc.shutdown(timeout=0.3)
    control.write_text("release-echo\n", encoding="utf-8")
    t.join(timeout=10)
    assert t.is_alive() is False
    assert errors
    assert all(isinstance(exc, LspProtocolError) for exc in errors)


def test_old_reader_eof_after_restart_keeps_new_pending(
    tmp_path: Path, controllable_lsp: tuple[Path, Path, Path]
) -> None:
    """After kill+restart, old reader EOF must not wipe the new generation table."""
    script, control, log = controllable_lsp
    proc = _proc(tmp_path, script, control, log, max_restarts=3)
    proc.ensure_initialized()
    old_gen = proc._transport_generation
    assert proc._proc is not None
    old_reader = proc._reader

    proc._proc.kill()
    proc._proc.wait(timeout=5)
    # Restart + handshake for the next request.
    control.write_text("release-echo\n", encoding="utf-8")
    result = proc.request("slow/echo", {})
    assert result == {"ok": True, "id": result["id"]}
    assert proc._transport_generation > old_gen
    # Old reader should have exited; new reader alive.
    if old_reader is not None:
        old_reader.join(timeout=5)
        assert old_reader.is_alive() is False
    assert proc._reader is not None
    assert proc._reader.is_alive()
    proc.shutdown()
