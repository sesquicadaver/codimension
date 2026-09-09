# -*- coding: utf-8 -*-
"""R243: CI/release/docs hardening — URI, risk confidence, SSH upload, LSP stress."""

from __future__ import annotations

import sys
import textwrap
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from core.risk_score import RiskInputs, compute_risk_score
from infrastructure.file_uri import file_uri_to_path, path_to_file_uri
from infrastructure.lsp_process import LspProcess, LspProcessKey
from utils.ssh_remote import FakeSftpSession, upload_file


def test_path_to_file_uri_roundtrip_special_chars(tmp_path: Path) -> None:
    path = tmp_path / "spa ce#hash?q%.py"
    path.write_text("x=1\n", encoding="utf-8")
    uri = path_to_file_uri(str(path))
    assert " " not in uri
    assert "%20" in uri
    assert "%23" in uri
    assert "%3F" in uri
    assert "%25" in uri
    restored = file_uri_to_path(uri)
    assert restored is not None
    assert Path(restored).resolve() == path.resolve()


def test_risk_confidence_uses_custom_weights() -> None:
    inputs = RiskInputs(lint_issues=0, max_cc=1.0, maintainability_index=90.0, git_churn=10)
    default = compute_risk_score(inputs)
    # Heavy git weight + missing metrics should drop confidence vs defaults.
    custom = compute_risk_score(
        RiskInputs(lint_issues=0, max_cc=None, maintainability_index=None, git_churn=10),
        weights={"lint": 0.1, "metrics": 0.1, "git": 0.8},
    )
    # With custom heavy git and no metrics, confidence is driven by git share.
    assert custom.confidence > 0.7
    # Default with full metrics+git should also be high; ensure custom path differs
    # from hard-coded 0.45/0.20 when metrics missing under heavy git.
    missing_default = compute_risk_score(
        RiskInputs(lint_issues=0, max_cc=None, maintainability_index=None, git_churn=10)
    )
    assert abs(custom.confidence - missing_default.confidence) > 0.05
    assert default.confidence >= missing_default.confidence


def test_ssh_upload_chunked_atomic_and_capped(tmp_path: Path) -> None:
    session = FakeSftpSession({"/": {}})
    session.makedirs("/proj")
    local = tmp_path / "payload.bin"
    local.write_bytes(b"abcdefghij" * 100)  # 1000 bytes
    upload_file(session, str(local), "/proj/payload.bin", max_bytes=10_000, chunk_size=64)
    assert session.files["/proj/payload.bin"] == local.read_bytes()
    leftovers = [p for p in session.files if "cdm-upload" in p or p.endswith(".cdm-replace-txn")]
    assert leftovers == []

    oversized = tmp_path / "big.bin"
    oversized.write_bytes(b"x" * 200)
    with pytest.raises(RuntimeError, match="size limit"):
        upload_file(session, str(oversized), "/proj/big.bin", max_bytes=50)


def test_ssh_upload_cancel(tmp_path: Path) -> None:
    session = FakeSftpSession({"/": {}})
    session.makedirs("/proj")
    local = tmp_path / "c.bin"
    local.write_bytes(b"y" * 500)

    def _cancel() -> bool:
        return True

    with pytest.raises(RuntimeError, match="cancelled"):
        upload_file(session, str(local), "/proj/c.bin", chunk_size=32, cancel=_cancel)


_FAST_LSP = textwrap.dedent(
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
                "result": {"capabilities": {}, "serverInfo": {"name": "fake-r243"}},
            })
        elif method == "shutdown":
            write_msg({"jsonrpc": "2.0", "id": mid, "result": None})
        elif method == "ping":
            write_msg({"jsonrpc": "2.0", "id": mid, "result": {"ok": True, "echo": msg.get("params")}})
        else:
            write_msg({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "no"}})
    """
)


@pytest.fixture()
def fast_lsp(tmp_path: Path) -> Path:
    script = tmp_path / "fast_lsp.py"
    script.write_text(_FAST_LSP, encoding="utf-8")
    return script


def test_lsp_concurrent_request_stress(tmp_path: Path, fast_lsp: Path) -> None:
    """R243: many overlapping requests complete without pending-map corruption."""
    proc = LspProcess(
        LspProcessKey("rust", str(tmp_path), ""),
        (sys.executable, str(fast_lsp)),
        allowlist=(sys.executable,),
        backoff_initial=0.01,
        request_timeout=5.0,
    )
    proc.ensure_initialized()
    errors: list[BaseException] = []
    results: list[object] = []

    def _one(i: int) -> None:
        try:
            results.append(proc.request("ping", {"n": i}, timeout=5.0))
        except BaseException as exc:  # noqa: BLE001 — collect for assertion
            errors.append(exc)

    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(_one, i) for i in range(24)]
        for fut in futs:
            fut.result(timeout=10.0)

    assert not errors
    assert len(results) == 24
    proc.shutdown()
