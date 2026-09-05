# -*- coding: utf-8 -*-
"""R210: LSP server→client requests (configuration, progress, register, applyEdit)."""

from __future__ import annotations

import sys
import textwrap
import time
from pathlib import Path

import pytest
from infrastructure.lsp_position_codec import LspPositionEncoding
from infrastructure.lsp_process import (
    LspProcess,
    LspProcessKey,
    LspProcessRegistry,
    default_client_capabilities,
)

_SERVER_REQUESTS_LSP = textwrap.dedent(
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

    def wait_response(expected_id, timeout=5.0):
        import time
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            msg = read_msg()
            if msg is None:
                raise SystemExit("eof waiting for response")
            if msg.get("id") == expected_id and ("result" in msg or "error" in msg):
                return msg
            # Client may still send requests (e.g. probe); answer probe later.
            if msg.get("method") == "probe/ping" and "id" in msg:
                write_msg({"jsonrpc": "2.0", "id": msg["id"], "result": {"ok": True}})
                continue
            if msg.get("method") in ("initialized", "$/cancelRequest", "exit"):
                if msg.get("method") == "exit":
                    raise SystemExit(0)
                continue
            if msg.get("method") == "shutdown" and "id" in msg:
                write_msg({"jsonrpc": "2.0", "id": msg["id"], "result": None})
                continue
        raise SystemExit("timeout waiting for response")

    client_caps = {}
    while True:
        msg = read_msg()
        if msg is None:
            break
        method = msg.get("method")
        mid = msg.get("id")
        if method == "exit":
            break
        if method == "initialized" or method == "$/cancelRequest":
            continue
        if mid is None:
            continue
        if method == "initialize":
            client_caps = (msg.get("params") or {}).get("capabilities") or {}
            write_msg({
                "jsonrpc": "2.0",
                "id": mid,
                "result": {
                    "capabilities": {"positionEncoding": "utf-8"},
                    "serverInfo": {"name": "fake-r210"},
                },
            })
            # After initialize result, fire server→client requests and require answers.
            write_msg({
                "jsonrpc": "2.0",
                "id": 9001,
                "method": "workspace/configuration",
                "params": {"items": [{"section": "rust-analyzer"}, {"section": "codimension"}]},
            })
            cfg = wait_response(9001)
            write_msg({
                "jsonrpc": "2.0",
                "id": 9002,
                "method": "window/workDoneProgress/create",
                "params": {"token": "t1"},
            })
            prog = wait_response(9002)
            write_msg({
                "jsonrpc": "2.0",
                "id": 9003,
                "method": "client/registerCapability",
                "params": {
                    "registrations": [{
                        "id": "reg-hover",
                        "method": "textDocument/hover",
                        "registerOptions": {},
                    }]
                },
            })
            reg = wait_response(9003)
            write_msg({
                "jsonrpc": "2.0",
                "id": 9004,
                "method": "workspace/applyEdit",
                "params": {
                    "label": "demo",
                    "edit": {"changes": {"file:///tmp/x.rs": []}},
                },
            })
            apply = wait_response(9004)
            write_msg({
                "jsonrpc": "2.0",
                "id": 9005,
                "method": "workspace/unknownThing",
                "params": {},
            })
            unknown = wait_response(9005)
            # Stash outcomes for probe
            outcomes = {
                "client_caps": client_caps,
                "configuration": cfg.get("result"),
                "progress": prog.get("result"),
                "register": reg.get("result"),
                "apply": apply.get("result"),
                "unknown_error": (unknown.get("error") or {}).get("code"),
            }
            # Keep answering until probe/ping asks for outcomes
            while True:
                msg2 = read_msg()
                if msg2 is None:
                    raise SystemExit(0)
                m2 = msg2.get("method")
                i2 = msg2.get("id")
                if m2 == "exit":
                    break
                if m2 == "initialized" or m2 == "$/cancelRequest":
                    continue
                if m2 == "shutdown" and i2 is not None:
                    write_msg({"jsonrpc": "2.0", "id": i2, "result": None})
                    continue
                if m2 == "probe/outcomes" and i2 is not None:
                    write_msg({"jsonrpc": "2.0", "id": i2, "result": outcomes})
                    continue
                if i2 is not None:
                    write_msg({
                        "jsonrpc": "2.0",
                        "id": i2,
                        "error": {"code": -32601, "message": f"unknown {m2}"},
                    })
            break
        elif method == "shutdown":
            write_msg({"jsonrpc": "2.0", "id": mid, "result": None})
        else:
            write_msg({
                "jsonrpc": "2.0",
                "id": mid,
                "error": {"code": -32601, "message": f"unknown {method}"},
            })
    """
)


@pytest.fixture()
def server_requests_lsp(tmp_path: Path) -> Path:
    path = tmp_path / "fake_r210_lsp.py"
    path.write_text(_SERVER_REQUESTS_LSP, encoding="utf-8")
    return path


def test_default_client_capabilities_advertise_r210_surfaces() -> None:
    caps = default_client_capabilities()
    assert caps["workspace"]["configuration"] is True
    assert caps["workspace"]["applyEdit"] is True
    assert caps["window"]["workDoneProgress"] is True
    assert LspPositionEncoding.UTF16.value in caps["general"]["positionEncodings"]


def test_server_to_client_requests_answered(
    tmp_path: Path,
    server_requests_lsp: Path,
) -> None:
    key = LspProcessKey("rust", str(tmp_path), "test")
    proc = LspProcess(
        key,
        (sys.executable, str(server_requests_lsp)),
        allowlist=(sys.executable,),
        request_timeout=10.0,
        max_restarts=0,
    )
    try:
        # initialize blocks until server finishes its request round-trip sequence
        # only after sending initialize result — but our fake fires requests
        # *before* client sends ``initialized``. The client ``initialize()``
        # waits for initialize response, then notifies initialized.
        # Server fires requests immediately after initialize result, which races
        # with the client's initialized notify — handled in wait_response.
        result = proc.initialize()
        assert result["capabilities"]["positionEncoding"] == "utf-8"
        assert proc.codec.encoding is LspPositionEncoding.UTF8

        # Give reader thread a moment to finish handling applyEdit / unknown.
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not proc.dynamic_registrations():
            time.sleep(0.02)
        regs = proc.dynamic_registrations()
        assert len(regs) == 1
        assert regs[0]["id"] == "reg-hover"

        previews = proc.drain_apply_edit_previews()
        assert len(previews) == 1
        assert previews[0]["label"] == "demo"

        outcomes = proc.request("probe/outcomes", None)
        assert outcomes["configuration"] == [None, None]
        assert outcomes["progress"] is None
        assert outcomes["register"] is None
        assert outcomes["apply"]["applied"] is False
        assert (
            "preview" in outcomes["apply"]["failureReason"].lower()
            or "apply" in outcomes["apply"]["failureReason"].lower()
        )
        assert outcomes["unknown_error"] == -32601
        workspace = outcomes["client_caps"].get("workspace") or {}
        assert workspace.get("configuration") is True
        assert workspace.get("applyEdit") is True
    finally:
        proc.shutdown()


def test_unregister_capability_drops_registration(
    tmp_path: Path,
) -> None:
    """Unit-level: register then unregister via dispatch helpers."""
    key = LspProcessKey("rust", str(tmp_path))
    # Avoid spawning: exercise _server_request_result directly.
    registry = LspProcessRegistry()
    proc = registry.get_or_create(
        key,
        (sys.executable, "-c", "pass"),
        allowlist=(sys.executable,),
    )
    assert (
        proc._server_request_result(
            "client/registerCapability",
            {"registrations": [{"id": "x", "method": "textDocument/hover"}]},
        )
        is None
    )
    assert len(proc.dynamic_registrations()) == 1
    assert (
        proc._server_request_result(
            "client/unregisterCapability",
            {"unregisterations": [{"id": "x", "method": "textDocument/hover"}]},
        )
        is None
    )
    assert proc.dynamic_registrations() == ()
