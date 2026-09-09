# -*- coding: utf-8 -*-
"""R255: durable SSH replace — UUID temps, phase recovery, classified posix_rename."""

from __future__ import annotations

import errno
import threading
from pathlib import Path

import pytest
from utils.ssh_remote import (
    FakeSftpSession,
    ReplaceTransaction,
    atomic_replace_remote,
    recover_replace_transaction,
    upload_file,
)


def _disable_posix(session: FakeSftpSession) -> None:
    def _unsupported(src: str, dst: str) -> None:
        raise OSError(errno.ENOTSUP, "posix_rename unsupported")

    session.posix_rename = _unsupported  # type: ignore[method-assign]
    session._cdm_posix_rename_supported = False  # type: ignore[attr-defined]


def test_r255_unique_staging_names_under_concurrent_upload(tmp_path: Path) -> None:
    session = FakeSftpSession({"/": {"proj": {"file.txt": b"base"}}})
    _disable_posix(session)
    staging_seen: list[str] = []
    real_write = session.write_file_chunks
    lock = threading.Lock()

    def tracking_write(path: str, chunks, *, max_bytes=None):
        with lock:
            if path.endswith(".partial"):
                staging_seen.append(path)
        return real_write(path, chunks, max_bytes=max_bytes)

    session.write_file_chunks = tracking_write  # type: ignore[method-assign]

    locals_ = []
    for i in range(4):
        p = tmp_path / f"f{i}.txt"
        p.write_bytes(f"payload-{i}".encode())
        locals_.append(p)

    errors: list[BaseException] = []

    def worker(local: Path) -> None:
        try:
            upload_file(session, str(local), "/proj/file.txt", max_bytes=10_000, chunk_size=8)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(p,)) for p in locals_]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert errors == []
    assert len(staging_seen) == 4
    assert len(set(staging_seen)) == 4
    assert session.files["/proj/file.txt"] in {b"payload-0", b"payload-1", b"payload-2", b"payload-3"}
    leftovers = [p for p in session.files if "cdm-upload" in p or p.endswith(".cdm-replace-txn")]
    assert leftovers == []


def test_r255_recover_restores_dest_after_crash_mid_swap() -> None:
    session = FakeSftpSession({"/": {"dest.txt": b"keep"}})
    _disable_posix(session)
    op_id = "deadbeef"
    staging = f"/dest.txt.cdm-upload-{op_id}.partial"
    backup = f"/dest.txt.cdm-upload-{op_id}.bak"
    session.files[staging] = b"new"
    # Simulate crash after dest → backup.
    session.files[backup] = session.files.pop("/dest.txt")
    txn = ReplaceTransaction(
        op_id=op_id,
        dest="/dest.txt",
        staging=staging,
        backup=backup,
        phase="dest_moved",
    )
    session.write_bytes("/dest.txt.cdm-replace-txn", txn.to_json_bytes())

    assert recover_replace_transaction(session, "/dest.txt") == "restored_backup"
    assert session.files.get("/dest.txt") == b"keep"
    assert staging not in session.files
    assert backup not in session.files
    assert "/dest.txt.cdm-replace-txn" not in session.files


def test_r255_posix_eio_does_not_blind_fallback() -> None:
    session = FakeSftpSession({"/": {"dest.txt": b"old", "staging.txt": b"new"}})

    def boom(src: str, dst: str) -> None:
        raise OSError(errno.EIO, "ambiguous network result")

    session.posix_rename = boom  # type: ignore[method-assign]

    with pytest.raises(OSError, match="ambiguous"):
        atomic_replace_remote(session, "/staging.txt", "/dest.txt", op_id="eio1")
    # Dest and staging unchanged — no backup-swap after ambiguous failure.
    assert session.files["/dest.txt"] == b"old"
    assert session.files["/staging.txt"] == b"new"


def test_r255_second_rename_failure_rolls_back(tmp_path: Path) -> None:
    session = FakeSftpSession({"/": {"dest.txt": b"keep", "staging.txt": b"new"}})
    _disable_posix(session)
    calls: list[tuple[str, str]] = []
    real_rename = session.rename

    def flaky_rename(src: str, dst: str) -> None:
        calls.append((src, dst))
        if len(calls) == 2:
            raise OSError(errno.EIO, "simulated second rename failure")
        real_rename(src, dst)

    session.rename = flaky_rename  # type: ignore[method-assign]

    with pytest.raises(OSError, match="simulated"):
        atomic_replace_remote(session, "/staging.txt", "/dest.txt", op_id="rb1")
    assert session.files.get("/dest.txt") == b"keep"
    assert "/dest.txt.cdm-replace-txn" not in session.files


def test_r255_upload_recovers_orphan_before_write(tmp_path: Path) -> None:
    session = FakeSftpSession({"/": {"proj": {"file.txt": b"v1"}}})
    _disable_posix(session)
    op_id = "orphan01"
    backup = f"/proj/file.txt.cdm-upload-{op_id}.bak"
    staging = f"/proj/file.txt.cdm-upload-{op_id}.partial"
    session.files[backup] = session.files.pop("/proj/file.txt")
    session.files[staging] = b"orphan-staging"
    txn = ReplaceTransaction(
        op_id=op_id,
        dest="/proj/file.txt",
        staging=staging,
        backup=backup,
        phase="dest_moved",
    )
    session.write_bytes("/proj/file.txt.cdm-replace-txn", txn.to_json_bytes())

    local = tmp_path / "file.txt"
    local.write_bytes(b"v2-after-recover")
    upload_file(session, str(local), "/proj/file.txt", max_bytes=10_000, chunk_size=8)
    assert session.files["/proj/file.txt"] == b"v2-after-recover"
    leftovers = [p for p in session.files if "cdm-upload" in p or p.endswith(".cdm-replace-txn")]
    assert leftovers == []
