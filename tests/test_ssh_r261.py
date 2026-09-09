# -*- coding: utf-8 -*-
"""R261: SSH replace state machine — intent phases, safe recovery, remote lock."""

from __future__ import annotations

import errno
from pathlib import Path

import pytest
import utils.ssh_remote as ssh_remote
from utils.ssh_remote import (
    FakeSftpSession,
    ReplaceTransaction,
    atomic_replace_remote,
    recover_replace_transaction,
)


def _disable_posix(session: FakeSftpSession) -> None:
    def _unsupported(src: str, dst: str) -> None:
        raise OSError(errno.ENOTSUP, "posix_rename unsupported")

    session.posix_rename = _unsupported  # type: ignore[method-assign]
    session._cdm_posix_rename_supported = False  # type: ignore[attr-defined]


@pytest.fixture(autouse=True)
def _clear_fault_hook():
    ssh_remote._replace_checkpoint_hook = None
    yield
    ssh_remote._replace_checkpoint_hook = None


def test_r261_crash_after_dest_to_backup_with_prepare_marker_restores() -> None:
    """Legacy/window: dest→backup done but marker still prepare/staged → restore."""
    session = FakeSftpSession({"/": {"dest.txt": b"keep"}})
    _disable_posix(session)
    op_id = "win001"
    staging = f"/dest.txt.cdm-upload-{op_id}.partial"
    backup = f"/dest.txt.cdm-upload-{op_id}.bak"
    session.files[staging] = b"new"
    session.files[backup] = session.files.pop("/dest.txt")
    txn = ReplaceTransaction(
        op_id=op_id,
        dest="/dest.txt",
        staging=staging,
        backup=backup,
        phase="staged",
    )
    session.write_bytes("/dest.txt.cdm-replace-txn", txn.to_json_bytes())

    assert recover_replace_transaction(session, "/dest.txt") == "restored_backup"
    assert session.files.get("/dest.txt") == b"keep"
    assert backup not in session.files
    assert staging not in session.files
    assert "/dest.txt.cdm-replace-txn" not in session.files


def test_r261_crash_after_dest_to_backup_before_dest_moved_marker() -> None:
    """Intent marker written; dest renamed; crash before dest_moved → auto-restore."""
    session = FakeSftpSession({"/": {"dest.txt": b"v1", "staging.txt": b"v2"}})
    _disable_posix(session)
    seen: list[str] = []

    def hook(name: str) -> None:
        seen.append(name)
        if name == "after_dest_to_backup":
            raise RuntimeError("injected crash after dest→backup")

    ssh_remote._replace_checkpoint_hook = hook
    with pytest.raises(RuntimeError, match="injected crash"):
        atomic_replace_remote(session, "/staging.txt", "/dest.txt", op_id="inj01")

    assert "after_intent_backup_marker" in seen
    assert "after_dest_to_backup" in seen
    # Exception path recovers: sole valid copy is the original content.
    assert session.files.get("/dest.txt") == b"v1"
    assert "/dest.txt.cdm-upload-inj01.bak" not in session.files
    assert "/dest.txt.cdm-replace-txn" not in session.files


def test_r261_never_deletes_backup_when_dest_missing() -> None:
    session = FakeSftpSession({"/": {}})
    _disable_posix(session)
    op_id = "solo01"
    backup = f"/dest.txt.cdm-upload-{op_id}.bak"
    staging = f"/dest.txt.cdm-upload-{op_id}.partial"
    session.files[backup] = b"only-copy"
    session.files[staging] = b"partial"
    txn = ReplaceTransaction(
        op_id=op_id,
        dest="/dest.txt",
        staging=staging,
        backup=backup,
        phase="prepare",
    )
    session.write_bytes("/dest.txt.cdm-replace-txn", txn.to_json_bytes())
    assert recover_replace_transaction(session, "/dest.txt") == "restored_backup"
    assert session.files["/dest.txt"] == b"only-copy"
    assert backup not in session.files


def test_r261_rejects_crafted_marker_foreign_paths() -> None:
    session = FakeSftpSession({"/": {"dest.txt": b"keep", "other.txt": b"x"}})
    _disable_posix(session)
    txn = ReplaceTransaction(
        op_id="evil01",
        dest="/dest.txt",
        staging="/other.txt",  # not upload sibling pattern — still same parent but
        backup="/other.txt.cdm-upload-evil01.bak",  # wrong backup name
        phase="prepare",
    )
    session.write_bytes("/dest.txt.cdm-replace-txn", txn.to_json_bytes())
    assert recover_replace_transaction(session, "/dest.txt") == "invalid_marker"
    assert session.files["/dest.txt"] == b"keep"
    assert session.files["/other.txt"] == b"x"
    with pytest.raises(RuntimeError, match="invalid replace marker"):
        atomic_replace_remote(session, "/staging-new.txt", "/dest.txt", op_id="n1")


def test_r261_marker_published_atomically(tmp_path: Path) -> None:
    session = FakeSftpSession({"/": {"dest.txt": b"old"}})
    _disable_posix(session)
    session.files["/staging.txt"] = b"new"
    atomic_replace_remote(session, "/staging.txt", "/dest.txt", op_id="atm01")
    assert session.files["/dest.txt"] == b"new"
    leftovers = [p for p in session.files if "cdm-replace" in p or "cdm-upload" in p]
    assert leftovers == []


def test_r261_remote_lock_blocks_second_replace() -> None:
    session = FakeSftpSession({"/": {"dest.txt": b"a", "s1.txt": b"b", "s2.txt": b"c"}})
    _disable_posix(session)
    # Hold lock as another IDE would.
    session.write_bytes(
        "/dest.txt.cdm-replace-lock",
        b'{"op_id":"other","pid":1,"ts":9999999999}\n',
    )
    with pytest.raises(RuntimeError, match="replace lock held"):
        atomic_replace_remote(session, "/s1.txt", "/dest.txt", op_id="blocked")
    assert session.files["/dest.txt"] == b"a"


def test_r261_fault_after_each_checkpoint_still_recoverable(tmp_path: Path) -> None:
    """Fault after every checkpoint must leave a recoverable sole-valid copy."""
    checkpoints = [
        "after_prepare_marker",
        "after_intent_backup_marker",
        "after_dest_to_backup",
        "after_dest_moved_marker",
        "after_staging_to_dest",
    ]
    for point in checkpoints:
        session = FakeSftpSession({"/": {"dest.txt": b"keep"}})
        _disable_posix(session)
        session.files["/staging.txt"] = b"new"

        def hook(name: str, *, stop=point) -> None:
            if name == stop:
                raise RuntimeError(f"fault:{stop}")

        ssh_remote._replace_checkpoint_hook = hook
        with pytest.raises(RuntimeError, match="fault:"):
            atomic_replace_remote(session, "/staging.txt", "/dest.txt", op_id=f"f{point[-4:]}")
        ssh_remote._replace_checkpoint_hook = None
        recover_replace_transaction(session, "/dest.txt")
        # Sole valid content must be the original keep OR successfully new — never empty.
        assert "/dest.txt" in session.files
        assert session.files["/dest.txt"] in {b"keep", b"new"}
