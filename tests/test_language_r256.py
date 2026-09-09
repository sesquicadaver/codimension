# -*- coding: utf-8 -*-
"""R256: LSP pending write rollback + URI NUL / O_NOFOLLOW hardening."""

from __future__ import annotations

import os
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import patch

import pytest
from infrastructure.file_uri import (
    file_uri_to_path,
    load_document_from_uri,
)
from infrastructure.lsp_framing import LspFramingError
from infrastructure.lsp_process import LspProcess, LspProcessKey


class _FakeStdin:
    def write(self, data: bytes) -> int:
        raise BrokenPipeError("simulated write failure")

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
    key = LspProcessKey("rust", "/tmp/r256-unit", "")
    return LspProcess(key, ("/bin/true",), allowlist=("/bin/true",))


def test_r256_bind_pending_rolls_back_on_write_failure() -> None:
    proc = _bare_proc()
    proc._proc = _FakeProc()  # type: ignore[assignment]
    proc._transport_generation = 1
    proc._initialized = True
    proc._generation = 1
    fut: Future = Future()
    with pytest.raises(Exception):
        proc._bind_pending_and_write(
            42,
            fut,
            {"jsonrpc": "2.0", "id": 42, "method": "ping"},
            require_initialized=True,
        )
    assert proc._pending == {}
    assert not fut.done()


def test_r256_bind_pending_rolls_back_on_encode_size_error() -> None:
    proc = _bare_proc()

    class _OkStdin:
        def write(self, data: bytes) -> int:
            return len(data)

        def flush(self) -> None:
            return None

    class _OkProc:
        def __init__(self) -> None:
            self.stdin = _OkStdin()

        def poll(self) -> int | None:
            return None

    proc._proc = _OkProc()  # type: ignore[assignment]
    proc._transport_generation = 2
    proc._initialized = True
    proc._generation = 2
    proc._max_message_bytes = 8
    fut: Future = Future()
    with pytest.raises(LspFramingError):
        proc._bind_pending_and_write(
            7,
            fut,
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "textDocument/hover",
                "params": {"pad": "x" * 100},
            },
            require_initialized=True,
        )
    assert proc._pending == {}


def test_r256_file_uri_rejects_embedded_nul() -> None:
    assert file_uri_to_path("file:///tmp/a%00.py") is None
    assert file_uri_to_path("file:///tmp/a\x00.py") is None
    assert file_uri_to_path("/tmp/a\x00.py") is None
    assert file_uri_to_path("file:///tmp/ok.py") == "/tmp/ok.py"


def test_r256_load_document_nul_uri_returns_none(tmp_path: Path) -> None:
    target = tmp_path / "ok.py"
    target.write_text("x = 1\n", encoding="utf-8")
    assert load_document_from_uri(f"file://{tmp_path}/a%00.py", workspace_root=str(tmp_path)) is None


def test_r256_direct_loader_never_retries_without_nofollow(tmp_path: Path) -> None:
    """Symlink open must fail closed — no second open() without O_NOFOLLOW."""
    real = tmp_path / "real.py"
    real.write_text("print(1)\n", encoding="utf-8")
    link = tmp_path / "link.py"
    link.symlink_to(real)
    uri = f"file://{link}"

    opens: list[int] = []
    real_open = os.open

    def tracking_open(path, flags, *args, **kwargs):
        opens.append(int(flags))
        return real_open(path, flags, *args, **kwargs)

    with patch("infrastructure.file_uri.os.open", side_effect=tracking_open):
        # No workspace root → direct loader path.
        result = load_document_from_uri(uri, workspace_root=None)

    assert result is None
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    assert nofollow != 0
    assert opens
    assert all(flags & nofollow for flags in opens)
