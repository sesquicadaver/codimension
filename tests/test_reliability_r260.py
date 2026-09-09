# -*- coding: utf-8 -*-
"""R260: reliability wave — LSP barriers, SSH crash phases, plugin, lifecycle."""

from __future__ import annotations

import errno
import json
import threading
import time
from concurrent.futures import Future
from pathlib import Path

import pytest
from app.services import ApplicationServices
from infrastructure.lsp_process import LspProcess, LspProcessKey, LspProtocolError
from plugins import policy
from plugins.policy import capture_plugin_file_identity, validate_candidate_before_import
from utils.ssh_remote import (
    FakeSftpSession,
    ReplaceTransaction,
    atomic_replace_remote,
    recover_replace_transaction,
)


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


def _bare_lsp() -> LspProcess:
    key = LspProcessKey("rust", "/tmp/r260-unit", "")
    return LspProcess(key, ("/bin/true",), allowlist=("/bin/true",))


def _disable_posix(session: FakeSftpSession) -> None:
    def _unsupported(src: str, dst: str) -> None:
        raise OSError(errno.ENOTSUP, "posix_rename unsupported")

    session.posix_rename = _unsupported  # type: ignore[method-assign]
    session._cdm_posix_rename_supported = False  # type: ignore[attr-defined]


def _minimal_cdm3(path: Path, *, uuid: str = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa") -> Path:
    payload = {
        "scriptname": "",
        "mddocfile": "",
        "creationdate": "",
        "author": "",
        "license": "",
        "copyright": "",
        "version": "1.0",
        "email": "",
        "description": "",
        "uuid": uuid,
        "importdirs": [],
        "excludeFromAnalysis": [],
        "excludeFromProjectTree": [],
        "slowScanPromptSeen": [],
        "encoding": "",
        "pythoninterpreter": "",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class _FakeProject:
    def __init__(self) -> None:
        self.loaded = False
        self.path = ""
        self.unloads = 0
        self.loads: list[str] = []
        self.fail_create = False

    def isLoaded(self) -> bool:
        return self.loaded

    def unloadProject(self, emitSignal: bool = True) -> None:
        del emitSignal
        self.unloads += 1
        self.loaded = False
        self.path = ""

    def loadProject(self, projectFile: str) -> None:
        self.loads.append(projectFile)
        self.loaded = True
        self.path = projectFile

    def createNew(self, fileName: str, props) -> None:
        del props
        if self.fail_create:
            raise RuntimeError("create boom")
        self.loads.append(fileName)
        self.loaded = True
        self.path = fileName


def test_r260_lsp_app_write_blocked_until_initialized() -> None:
    """Application write lease rejects when handshake has not completed."""
    proc = _bare_lsp()
    proc._proc = _FakeProc()  # type: ignore[assignment]
    proc._transport_generation = 1
    proc._initialized = False
    with pytest.raises(LspProtocolError, match="not initialized"):
        proc._write(
            {"jsonrpc": "2.0", "method": "textDocument/didOpen", "params": {}},
            require_initialized=True,
        )
    assert proc._proc.stdin.chunks == []


def test_r260_lsp_notify_blocks_while_lifecycle_lock_held() -> None:
    """While handshake holds lifecycle_lock, app notify write cannot sneak in."""
    proc = _bare_lsp()
    proc._proc = _FakeProc()  # type: ignore[assignment]
    proc._transport_generation = 4
    proc._initialized = False
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def handshake_holder() -> None:
        with proc._lifecycle_lock:
            barrier.wait(timeout=5)
            time.sleep(0.2)

    def app_notify() -> None:
        barrier.wait(timeout=5)
        try:
            proc._write(
                {"jsonrpc": "2.0", "method": "workspace/didChangeConfiguration"},
                require_initialized=True,
            )
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    t1 = threading.Thread(target=handshake_holder)
    t2 = threading.Thread(target=app_notify)
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)
    assert len(errors) == 1
    assert isinstance(errors[0], LspProtocolError)
    assert "not initialized" in str(errors[0])
    assert proc._proc.stdin.chunks == []


def test_r260_lsp_pending_rollback_leaves_no_orphan_future() -> None:
    """Write failure after bind must drop pending (R256 residual under reliability wave)."""

    class _BoomStdin:
        def write(self, data: bytes) -> int:
            raise BrokenPipeError("pipe")

        def flush(self) -> None:
            return None

    class _BoomProc:
        def __init__(self) -> None:
            self.stdin = _BoomStdin()

        def poll(self) -> int | None:
            return None

    proc = _bare_lsp()
    proc._proc = _BoomProc()  # type: ignore[assignment]
    proc._transport_generation = 2
    proc._initialized = True
    proc._generation = 2
    fut: Future = Future()
    with pytest.raises(LspProtocolError, match="stdin closed"):
        proc._bind_pending_and_write(
            9,
            fut,
            {"jsonrpc": "2.0", "id": 9, "method": "ping"},
            require_initialized=True,
        )
    assert proc._pending == {}
    assert not fut.done()


def test_r260_ssh_recover_staged_abandons_orphan() -> None:
    session = FakeSftpSession({"/": {"dest.txt": b"keep"}})
    _disable_posix(session)
    op_id = "stage01"
    staging = f"/dest.txt.cdm-upload-{op_id}.partial"
    backup = f"/dest.txt.cdm-upload-{op_id}.bak"
    session.files[staging] = b"partial"
    txn = ReplaceTransaction(
        op_id=op_id,
        dest="/dest.txt",
        staging=staging,
        backup=backup,
        phase="staged",
    )
    session.write_bytes("/dest.txt.cdm-replace-txn", txn.to_json_bytes())
    assert recover_replace_transaction(session, "/dest.txt") == "abandoned"
    assert session.files.get("/dest.txt") == b"keep"
    assert staging not in session.files
    assert "/dest.txt.cdm-replace-txn" not in session.files


def test_r260_ssh_recover_committed_cleans_artifacts() -> None:
    session = FakeSftpSession({"/": {"dest.txt": b"new"}})
    _disable_posix(session)
    op_id = "commit1"
    staging = f"/dest.txt.cdm-upload-{op_id}.partial"
    backup = f"/dest.txt.cdm-upload-{op_id}.bak"
    session.files[staging] = b"stale"
    session.files[backup] = b"old"
    txn = ReplaceTransaction(
        op_id=op_id,
        dest="/dest.txt",
        staging=staging,
        backup=backup,
        phase="committed",
    )
    session.write_bytes("/dest.txt.cdm-replace-txn", txn.to_json_bytes())
    assert recover_replace_transaction(session, "/dest.txt") == "cleanup"
    assert session.files.get("/dest.txt") == b"new"
    assert staging not in session.files
    assert backup not in session.files
    assert "/dest.txt.cdm-replace-txn" not in session.files


def test_r260_ssh_recover_dest_moved_finalize_when_dest_present() -> None:
    """Crash after staging→dest succeeded: clear marker/backup without rewind."""
    session = FakeSftpSession({"/": {"dest.txt": b"new"}})
    _disable_posix(session)
    op_id = "fin001"
    staging = f"/dest.txt.cdm-upload-{op_id}.partial"
    backup = f"/dest.txt.cdm-upload-{op_id}.bak"
    session.files[backup] = b"old"
    txn = ReplaceTransaction(
        op_id=op_id,
        dest="/dest.txt",
        staging=staging,
        backup=backup,
        phase="dest_moved",
    )
    session.write_bytes("/dest.txt.cdm-replace-txn", txn.to_json_bytes())
    assert recover_replace_transaction(session, "/dest.txt") == "finalize"
    assert session.files.get("/dest.txt") == b"new"
    assert backup not in session.files
    assert "/dest.txt.cdm-replace-txn" not in session.files


def test_r260_ssh_crash_before_second_rename_restores_via_recover() -> None:
    """Simulate dest_moved crash then recovery before a fresh replace."""
    session = FakeSftpSession({"/": {"dest.txt": b"v1", "staging.txt": b"v2"}})
    _disable_posix(session)
    op_id = "midswp"
    staging = "/staging.txt"
    backup = f"/dest.txt.cdm-upload-{op_id}.bak"
    # Crash after dest→backup; staging still holds new bytes.
    session.files[backup] = session.files.pop("/dest.txt")
    session.files[staging] = b"v2"
    txn = ReplaceTransaction(
        op_id=op_id,
        dest="/dest.txt",
        staging=staging,
        backup=backup,
        phase="dest_moved",
    )
    session.write_bytes("/dest.txt.cdm-replace-txn", txn.to_json_bytes())
    assert recover_replace_transaction(session, "/dest.txt") == "restored_backup"
    assert session.files["/dest.txt"] == b"v1"
    # Fresh replace after recovery.
    session.files["/staging2.txt"] = b"v3"
    atomic_replace_remote(session, "/staging2.txt", "/dest.txt", op_id="ok2")
    assert session.files["/dest.txt"] == b"v3"


def test_r260_plugin_oversized_package_denies_import(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(policy, "_MAX_PLUGIN_FILE_BYTES", 48)
    monkeypatch.setattr(policy, "_MAX_PLUGIN_PACKAGE_TOTAL_BYTES", 96)
    info = tmp_path / "plug.cdmp"
    info.write_text(
        "[Core]\nName = Big\nModule = __init__\n"
        "[Codimension]\nCategory = WizardInterface\nMinIDEVersion = 5.0.0\n"
        "MinPluginAPI = 1\nRequiredCapabilities =\nEntrypoint = __init__\n",
        encoding="utf-8",
    )
    (tmp_path / "__init__.py").write_text("X = 1\n", encoding="utf-8")
    (tmp_path / "blob.py").write_bytes(b"Z" * 80)
    identity = capture_plugin_file_identity(
        info_path=str(info),
        module_filepath=str(tmp_path / "__init__"),
    )
    assert identity.valid is False
    decision = validate_candidate_before_import(
        info_path=str(info),
        module_filepath=str(tmp_path / "__init__"),
        name="Big",
        version="1",
        plugin_path=str(tmp_path),
        expected_identity=None,
        ide_version="99.0.0",
        require_manifest=False,
    )
    assert decision.ok is False


def test_r260_lifecycle_create_failure_restores_previous(tmp_path: Path) -> None:
    old = _minimal_cdm3(tmp_path / "old.cdm3")
    project = _FakeProject()
    services = ApplicationServices(project, prevalidate=True)
    assert services.load_project(str(old)) is True
    project.fail_create = True
    with pytest.raises(RuntimeError, match="create boom"):
        services.create_project(str(tmp_path / "new.cdm3"), {"author": "r260"})
    assert project.loaded is True
    assert project.path == str(old)
