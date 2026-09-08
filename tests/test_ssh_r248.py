# -*- coding: utf-8 -*-
"""R248: SSH atomic replace — posix_rename / backup-swap; Fake matches SFTP."""

from __future__ import annotations

import errno
from pathlib import Path

import pytest
from utils.ssh_remote import (
    FakeSftpSession,
    atomic_replace_remote,
    upload_file,
)


def test_fake_rename_refuses_existing_dest() -> None:
    session = FakeSftpSession({"/": {"a.bin": b"old", "b.bin": b"new"}})
    with pytest.raises(OSError) as excinfo:
        session.rename("/b.bin", "/a.bin")
    assert excinfo.value.errno == errno.EEXIST
    assert session.files["/a.bin"] == b"old"
    assert session.files["/b.bin"] == b"new"


def test_fake_posix_rename_replaces_dest() -> None:
    session = FakeSftpSession({"/": {"a.bin": b"old", "b.bin": b"new"}})
    session.posix_rename("/b.bin", "/a.bin")
    assert session.files["/a.bin"] == b"new"
    assert "/b.bin" not in session.files


def test_upload_overwrites_existing_via_posix_rename(tmp_path: Path) -> None:
    session = FakeSftpSession({"/": {"proj": {"file.txt": b"v1"}}})
    local = tmp_path / "file.txt"
    local.write_bytes(b"v2-content")
    upload_file(session, str(local), "/proj/file.txt", max_bytes=10_000, chunk_size=8)
    assert session.files["/proj/file.txt"] == b"v2-content"
    assert "/proj/file.txt.cdm-upload-partial" not in session.files
    assert "/proj/file.txt.cdm-upload-bak" not in session.files


def test_upload_backup_swap_without_posix_rename(tmp_path: Path) -> None:
    """When posix_rename is unavailable, overwrite uses rename backup-swap (R248)."""
    session = FakeSftpSession({"/": {"proj": {"file.txt": b"v1"}}})

    def _unsupported(src: str, dst: str) -> None:
        raise OSError(errno.ENOTSUP, "posix_rename unsupported")

    session.posix_rename = _unsupported  # type: ignore[method-assign]

    local = tmp_path / "file.txt"
    local.write_bytes(b"v2-via-swap")
    upload_file(session, str(local), "/proj/file.txt", max_bytes=10_000, chunk_size=8)
    assert session.files["/proj/file.txt"] == b"v2-via-swap"
    assert "/proj/file.txt.cdm-upload-partial" not in session.files
    assert "/proj/file.txt.cdm-upload-bak" not in session.files


def test_atomic_replace_rollback_restores_dest_on_second_rename_failure() -> None:
    session = FakeSftpSession({"/": {"dest.txt": b"keep", "staging.txt": b"new"}})
    calls: list[tuple[str, str]] = []
    real_rename = session.rename

    def flaky_rename(src: str, dst: str) -> None:
        calls.append((src, dst))
        if len(calls) == 2:
            raise OSError(errno.EIO, "simulated second rename failure")
        real_rename(src, dst)

    session.rename = flaky_rename  # type: ignore[method-assign]

    def _unsupported(src: str, dst: str) -> None:
        raise OSError(errno.ENOTSUP, "posix_rename unsupported")

    session.posix_rename = _unsupported  # type: ignore[method-assign]

    with pytest.raises(OSError, match="simulated"):
        atomic_replace_remote(session, "/staging.txt", "/dest.txt")
    assert session.files.get("/dest.txt") == b"keep"
    assert "/staging.txt" in session.files
