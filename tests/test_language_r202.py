# -*- coding: utf-8 -*-
"""R202: LANGUAGE_SERVER_SPAWN gate + LspProcess stdio JSON-RPC."""

from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path

import pytest
from app.language_services import LanguageServiceManager
from core.language_policy import (
    LanguageServerSpawnError,
    PolicyCapability,
    require_language_server_spawn,
)
from infrastructure.lsp_framing import LspFramingError, encode_message, read_message
from infrastructure.lsp_process import (
    LspProcess,
    LspProcessKey,
    LspProcessRegistry,
    LspProcessState,
    LspProtocolError,
)

# Minimal fake LSP server: initialize, echo, cancel, shutdown/exit.
_FAKE_LSP = textwrap.dedent(
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

    cancelled = set()
    while True:
        msg = read_msg()
        if msg is None:
            break
        method = msg.get("method")
        mid = msg.get("id")
        if method == "$/cancelRequest":
            cancelled.add((msg.get("params") or {}).get("id"))
            continue
        if method == "exit":
            break
        if mid is None:
            continue
        if method == "initialize":
            write_msg({
                "jsonrpc": "2.0",
                "id": mid,
                "result": {
                    "capabilities": {},
                    "serverInfo": {"name": "fake-lsp"},
                },
            })
        elif method == "shutdown":
            write_msg({"jsonrpc": "2.0", "id": mid, "result": None})
        elif method == "echo":
            write_msg({
                "jsonrpc": "2.0",
                "id": mid,
                "result": {"echo": (msg.get("params") or {}).get("value"), "cancelled": mid in cancelled},
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
def fake_lsp_script(tmp_path: Path) -> Path:
    path = tmp_path / "fake_lsp.py"
    path.write_text(_FAKE_LSP, encoding="utf-8")
    return path


def test_policy_capability_spawn_tag() -> None:
    assert PolicyCapability.LANGUAGE_SERVER_SPAWN.value == "language_server_spawn"


def test_spawn_gate_rejects_relative_and_missing_allowlist(tmp_path: Path) -> None:
    binary = tmp_path / "server"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    with pytest.raises(LanguageServerSpawnError, match="absolute"):
        require_language_server_spawn("server", [str(binary)])
    with pytest.raises(LanguageServerSpawnError, match="allowlist"):
        require_language_server_spawn(str(binary), [])


def test_spawn_gate_accepts_allowlisted_absolute(tmp_path: Path) -> None:
    binary = tmp_path / "server"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    assert require_language_server_spawn(str(binary), [str(binary)]) == os.path.realpath(binary)


def test_framing_roundtrip(tmp_path: Path) -> None:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
    frame = encode_message(payload)
    pipe = tmp_path / "frame.bin"
    pipe.write_bytes(frame)
    with pipe.open("rb") as handle:
        assert read_message(handle) == payload


def test_framing_rejects_oversized() -> None:
    import io

    huge = b"Content-Length: 99999999\r\n\r\n"
    with pytest.raises(LspFramingError, match="exceeds"):
        read_message(io.BytesIO(huge), max_message_bytes=1024)


def test_lsp_process_initialize_echo_shutdown(tmp_path: Path, fake_lsp_script: Path) -> None:
    key = LspProcessKey("rust", str(tmp_path), "cargo:default")
    allow = [sys.executable]
    proc = LspProcess(
        key,
        [sys.executable, str(fake_lsp_script)],
        allowlist=allow,
        request_timeout=5.0,
        backoff_initial=0.01,
    )
    assert proc.state is LspProcessState.IDLE
    result = proc.initialize()
    assert result["serverInfo"]["name"] == "fake-lsp"
    assert proc.initialized
    echoed = proc.request("echo", {"value": "hi"})
    assert echoed == {"echo": "hi", "cancelled": False}
    proc.shutdown()
    assert proc.state is LspProcessState.STOPPED


def test_lsp_process_denies_spawn_without_allowlist(tmp_path: Path, fake_lsp_script: Path) -> None:
    key = LspProcessKey("cpp", str(tmp_path))
    proc = LspProcess(
        key,
        [sys.executable, str(fake_lsp_script)],
        allowlist=[],
    )
    with pytest.raises(LanguageServerSpawnError):
        proc.start()


def test_lsp_registry_one_per_key(tmp_path: Path, fake_lsp_script: Path) -> None:
    registry = LspProcessRegistry()
    key_a = LspProcessKey("rust", str(tmp_path), "a")
    key_b = LspProcessKey("rust", str(tmp_path), "b")
    allow = [sys.executable]
    cmd = [sys.executable, str(fake_lsp_script)]
    p1 = registry.get_or_create(key_a, cmd, allowlist=allow)
    p1b = registry.get_or_create(key_a, cmd, allowlist=allow)
    p2 = registry.get_or_create(key_b, cmd, allowlist=allow)
    assert p1 is p1b
    assert p1 is not p2
    p1.initialize()
    p2.initialize()
    registry.shutdown_workspace(str(tmp_path))
    assert registry.keys() == ()


def test_manager_shutdown_clears_lsp_registry() -> None:
    mgr = LanguageServiceManager()
    assert mgr.lsp_processes.keys() == ()
    mgr.shutdown()


def test_unknown_method_raises_protocol_error(tmp_path: Path, fake_lsp_script: Path) -> None:
    proc = LspProcess(
        LspProcessKey("rust", str(tmp_path)),
        [sys.executable, str(fake_lsp_script)],
        allowlist=[sys.executable],
        request_timeout=5.0,
    )
    proc.initialize()
    with pytest.raises(LspProtocolError, match="unknown"):
        proc.request("nope")
    proc.shutdown()
