# -*- coding: utf-8 -*-
"""SSH remote runtime: path map, SYNC_* jobs, caps (no network)."""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import parsers  # noqa: E402,F401
import pytest

_CODIM = Path(__file__).resolve().parents[1] / "codimension"


def _under_codimension(mod: object) -> bool:
    path = getattr(mod, "__file__", None)
    if path:
        return "/codimension/" in os.path.abspath(path).replace("\\", "/")
    return False


@pytest.fixture(autouse=True)
def _purge_stubs():
    import importlib

    dirty = False
    for name in list(sys.modules):
        if name not in ("ui", "utils") and not name.startswith(("ui.", "utils.")):
            continue
        mod = sys.modules[name]
        if _under_codimension(mod):
            continue
        del sys.modules[name]
        dirty = True
    if dirty:
        importlib.invalidate_caches()
        if str(_CODIM) not in sys.path:
            sys.path.insert(0, str(_CODIM))
    yield
    from utils import ssh_project_runtime as rt

    rt.clear_sync_state()
    with rt._jobs_lock:
        for handle in list(rt._upload_jobs.values()):
            handle.request_cancel()
        rt._upload_jobs.clear()
        if rt._run_job is not None:
            rt._run_job.request_cancel()
            rt._run_job = None


def _binding(tmp_path):
    from utils.ssh_remote import RemoteProjectBinding

    local_root = tmp_path / "cache"
    local_root.mkdir()
    return RemoteProjectBinding(
        profile_id="p1",
        host="h",
        port=22,
        user="u",
        auth="key",
        identity_file="",
        remote_root="/r",
        remote_cdm3="/r/r.cdm3",
        local_root=str(local_root),
        local_cdm3=str(local_root / "r.cdm3"),
    ), local_root


def test_map_local_to_remote(tmp_path):
    from utils.ssh_project_runtime import is_under_binding, map_local_to_remote

    binding, local_root = _binding(tmp_path)
    script = local_root / "pkg" / "main.py"
    script.parent.mkdir()
    script.write_text("print(1)\n", encoding="utf-8")

    assert map_local_to_remote(binding, str(script)) == "/r/pkg/main.py"
    assert is_under_binding(binding, str(script))
    assert not is_under_binding(binding, str(tmp_path / "other.py"))


def test_upload_via_fake(tmp_path):
    from utils.ssh_project_runtime import map_local_to_remote
    from utils.ssh_remote import FakeSftpSession, upload_file

    binding, local_root = _binding(tmp_path)
    local = local_root / "a.py"
    local.write_text("x=1\n", encoding="utf-8")
    remote = map_local_to_remote(binding, str(local))
    session = FakeSftpSession()
    session.makedirs("/r")
    upload_file(session, str(local), remote)
    assert session.read_bytes(remote) == b"x=1\n"


def test_r186_default_job_limits_nonzero():
    from utils.ssh_project_runtime import (
        DEFAULT_SSH_JOB_TIMEOUT_SEC,
        DEFAULT_SSH_MAX_OUTPUT_BYTES,
        resolve_ssh_job_limits,
    )

    assert DEFAULT_SSH_JOB_TIMEOUT_SEC > 0
    assert DEFAULT_SSH_MAX_OUTPUT_BYTES > 0
    timeout, cap = resolve_ssh_job_limits()
    assert timeout == DEFAULT_SSH_JOB_TIMEOUT_SEC
    assert cap == DEFAULT_SSH_MAX_OUTPUT_BYTES


def test_r186_async_upload_reaches_synced(tmp_path, monkeypatch):
    from utils import ssh_project_runtime as rt
    from utils.ssh_remote import FakeSftpSession

    binding, local_root = _binding(tmp_path)
    local = local_root / "a.py"
    local.write_text("x=1\n", encoding="utf-8")
    remote = rt.map_local_to_remote(binding, str(local))
    session = FakeSftpSession()
    session.makedirs("/r")

    def fake_with_sftp(_binding, fn, **_kwargs):
        fn(session)

    monkeypatch.setattr(rt, "_with_sftp", fake_with_sftp)
    assert rt.get_sync_state(str(local)) == rt.SYNC_LOCAL
    handle = rt.schedule_remote_upload(binding, str(local), remote)
    assert handle.join(5.0)
    assert rt.get_sync_state(str(local)) == rt.SYNC_SYNCED
    assert session.read_bytes(remote) == b"x=1\n"
    # Local save success must not be confused with SYNCED — state API is the signal.
    assert rt.SYNC_LOCAL != rt.SYNC_SYNCED


def test_r186_async_upload_failure_sets_sync_failed(tmp_path, monkeypatch):
    from utils import ssh_project_runtime as rt

    binding, local_root = _binding(tmp_path)
    local = local_root / "a.py"
    local.write_text("x=1\n", encoding="utf-8")
    remote = rt.map_local_to_remote(binding, str(local))

    def boom(_binding, fn, **_kwargs):
        raise RuntimeError("sftp down")

    monkeypatch.setattr(rt, "_with_sftp", boom)
    handle = rt.schedule_remote_upload(binding, str(local), remote)
    assert handle.join(5.0)
    assert rt.get_sync_state(str(local)) == rt.SYNC_FAILED
    assert handle.error is not None


def test_r186_cancel_upload(tmp_path, monkeypatch):
    from utils import ssh_project_runtime as rt

    binding, local_root = _binding(tmp_path)
    local = local_root / "a.py"
    local.write_text("x=1\n", encoding="utf-8")
    remote = rt.map_local_to_remote(binding, str(local))
    started = threading.Event()

    def slow_sftp(_binding, fn, **kwargs):
        started.set()
        cancel = kwargs.get("cancel")
        while cancel is not None and not cancel.is_set():
            time.sleep(0.02)
        raise rt.SshRemoteJobCancelled("SSH upload cancelled")

    monkeypatch.setattr(rt, "_with_sftp", slow_sftp)
    handle = rt.schedule_remote_upload(binding, str(local), remote)
    assert started.wait(2.0)
    assert rt.cancel_ssh_upload(str(local))
    assert handle.join(5.0)
    assert rt.get_sync_state(str(local)) == rt.SYNC_CANCELLED


def test_r186_append_capped():
    from utils.ssh_project_runtime import _append_capped

    buf, trunc = _append_capped(bytearray(), b"abcdef", 4, False)
    assert bytes(buf) == b"abcd"
    assert trunc is True
    buf2, trunc2 = _append_capped(buf, b"xyz", 4, trunc)
    assert bytes(buf2) == b"abcd"
    assert trunc2 is True


def test_r186_schedule_run_async(tmp_path, monkeypatch):
    from utils import ssh_project_runtime as rt

    binding, local_root = _binding(tmp_path)
    script = local_root / "main.py"
    script.write_text("print(1)\n", encoding="utf-8")

    def fake_run(*_a, **_k):
        return 0, "ok\n", "", "/r/main.py"

    monkeypatch.setattr(rt, "run_remote_script", fake_run)
    monkeypatch.setattr(rt, "_call_on_gui_thread", lambda fn: fn())
    monkeypatch.setattr(rt, "_emit_run_output", lambda *a, **k: None)
    finished = threading.Event()
    results: list = []

    def on_finished(code, stdout, stderr, remote, err):
        results.append((code, stdout, stderr, remote, err))
        finished.set()

    handle = rt.schedule_remote_run(binding, str(script), on_finished=on_finished)
    assert handle.join(5.0)
    assert finished.wait(2.0)
    assert results[0][0] == 0
    assert results[0][1] == "ok\n"
    assert results[0][4] is None
