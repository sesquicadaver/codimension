# -*- coding: utf-8 -*-
"""R198: SSH IDE debug plan / Fake tunnel / path-map contracts."""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import parsers  # noqa: F401
import pytest

_ROOT = Path(__file__).resolve().parents[1]
_CODIM = _ROOT / "codimension"


@pytest.fixture(autouse=True)
def _purge_stubs():
    import importlib

    dirty = False
    for name in list(sys.modules):
        if name not in ("ui", "utils") and not name.startswith(("ui.", "utils.")):
            continue
        mod = sys.modules[name]
        path = getattr(mod, "__file__", "") or ""
        if "/codimension/" in path.replace("\\", "/"):
            continue
        del sys.modules[name]
        dirty = True
    if dirty:
        importlib.invalidate_caches()
        if str(_CODIM) not in sys.path:
            sys.path.insert(0, str(_CODIM))
    yield
    from utils.ssh_ide_debug import set_ssh_debug_path_mapper

    set_ssh_debug_path_mapper(None)


def _binding(tmp_path: Path):
    from utils.ssh_remote import RemoteProjectBinding

    local_root = tmp_path / "cache"
    local_root.mkdir()
    script = local_root / "app.py"
    script.write_text("x = 1\n", encoding="utf-8")
    return (
        RemoteProjectBinding(
            profile_id="host1",
            host="example.test",
            port=22,
            user="u",
            auth="key",
            identity_file="",
            remote_root="/remote/proj",
            remote_cdm3="/remote/proj/p.cdm3",
            local_root=str(local_root),
            local_cdm3=str(local_root / "p.cdm3"),
        ),
        script,
    )


def test_prepare_ssh_ide_debug_plan_argv_and_tunnel(tmp_path):
    from utils.ssh_ide_debug import REMOTE_CLIENT_DIR, prepare_ssh_ide_debug_plan

    binding, script = _binding(tmp_path)
    plan = prepare_ssh_ide_debug_plan(
        binding,
        str(script),
        tcp_port=4242,
        procuuid="uuid-1",
        arguments=["--flag"],
    )
    assert plan.tunnel.remote_port == 4242
    assert plan.tunnel.local_port == 4242
    assert plan.remote_script == "/remote/proj/app.py"
    assert REMOTE_CLIENT_DIR in plan.remote_client_script
    assert plan.argv[0] == "python3"
    assert "client_cdm_dbg.py" in plan.argv[1]
    assert plan.argv[plan.argv.index("--host") + 1] == "127.0.0.1"
    assert plan.argv[plan.argv.index("--port") + 1] == "4242"
    assert plan.argv[plan.argv.index("--procuuid") + 1] == "uuid-1"
    dash = plan.argv.index("--")
    assert plan.argv[dash + 1] == "/remote/proj/app.py"
    assert plan.argv[dash + 2] == "--flag"
    assert any(remote.endswith("client_cdm_dbg.py") for _local, remote in plan.upload_pairs)
    assert plan.metadata["backend"] == "ssh-ide-debug"


def test_path_map_roundtrip(tmp_path):
    from utils.ssh_ide_debug import (
        make_binding_path_mapper,
        map_remote_to_local,
        remap_debug_filename,
        remap_debug_stack,
        set_ssh_debug_path_mapper,
    )
    from utils.ssh_project_runtime import map_local_to_remote

    binding, script = _binding(tmp_path)
    remote = map_local_to_remote(binding, str(script))
    assert map_remote_to_local(binding, remote) == os.path.realpath(script)
    set_ssh_debug_path_mapper(make_binding_path_mapper(binding))
    assert remap_debug_filename(remote) == os.path.realpath(script)
    stack = remap_debug_stack([[remote, "3", "f"]])
    assert stack[0][0] == os.path.realpath(script)
    assert stack[0][1] == "3"


def test_fake_reverse_tunnel_records_open():
    from utils.ssh_ide_debug import REMOTE_TUNNEL_BIND, FakeReverseTunnel, ReverseTunnelSpec

    tunnel = FakeReverseTunnel()
    spec = ReverseTunnelSpec(remote_port=9, local_port=9)
    tunnel.open(spec)
    tunnel.close()
    assert tunnel.opened == [spec]
    assert tunnel.closed == 1
    assert spec.remote_bind == REMOTE_TUNNEL_BIND


def test_r212_map_remote_rejects_dotdot_escape(tmp_path):
    """R212: ``..`` in remote path must not escape the local cache."""
    from utils.ssh_ide_debug import map_remote_to_local

    binding, _script = _binding(tmp_path)
    with pytest.raises(ValueError, match="outside project root|escapes"):
        map_remote_to_local(binding, "/remote/proj/../../etc/passwd")
    with pytest.raises(ValueError, match="outside project root|escapes"):
        map_remote_to_local(binding, "/remote/proj/foo/../../../etc/passwd")


def test_r212_map_remote_containment_after_realpath(tmp_path):
    from utils.ssh_ide_debug import map_remote_to_local

    binding, script = _binding(tmp_path)
    mapped = map_remote_to_local(binding, "/remote/proj/app.py")
    assert mapped == os.path.realpath(script)
    # Nested path under root still contained.
    nested = tmp_path / "cache" / "pkg"
    nested.mkdir()
    (nested / "mod.py").write_text("y=2\n", encoding="utf-8")
    mapped2 = map_remote_to_local(binding, "/remote/proj/pkg/mod.py")
    assert mapped2 == os.path.realpath(nested / "mod.py")
    assert os.path.commonpath([os.path.realpath(binding.local_root), mapped2]) == os.path.realpath(binding.local_root)


def test_r212_paramiko_tunnel_binds_loopback(monkeypatch):
    """R212: request/cancel_port_forward must use 127.0.0.1, not \"\"."""
    from utils.ssh_ide_debug import REMOTE_TUNNEL_BIND, ParamikoReverseTunnel, ReverseTunnelSpec

    calls: list[tuple] = []

    class _Transport:
        def request_port_forward(self, address, port):
            calls.append(("request", address, port))

        def cancel_port_forward(self, address, port):
            calls.append(("cancel", address, port))

        def accept(self, _timeout):
            return None

    class _Client:
        def get_transport(self):
            return _Transport()

    tunnel = ParamikoReverseTunnel(_Client())
    # Avoid starting a long-lived acceptor: open then close quickly.
    original_thread = threading.Thread

    class _InstantThread:
        def __init__(self, *a, **k):
            del a, k

        def start(self):
            return None

        def join(self, timeout=None):
            del timeout

    import utils.ssh_ide_debug as ide

    monkeypatch.setattr(ide.threading, "Thread", _InstantThread)
    tunnel.open(ReverseTunnelSpec(remote_port=4242, local_port=4242))
    tunnel.close()
    assert ("request", REMOTE_TUNNEL_BIND, 4242) in calls
    assert ("cancel", REMOTE_TUNNEL_BIND, 4242) in calls
    monkeypatch.setattr(ide.threading, "Thread", original_thread)


def test_r212_exec_argv_honours_cancel_and_sleeps():
    """R212: poll loop sleeps and exits promptly when cancel is set."""
    import threading
    import time

    from utils.ssh_ide_debug import _exec_argv

    sleeps: list[float] = []

    class _Channel:
        def __init__(self):
            self._n = 0

        def settimeout(self, _t):
            return None

        def exec_command(self, _cmd):
            return None

        def recv_ready(self):
            return False

        def recv_stderr_ready(self):
            return False

        def exit_status_ready(self):
            return False

        def recv(self, _n):
            return b""

        def recv_stderr(self, _n):
            return b""

        def recv_exit_status(self):
            return 0

        def close(self):
            return None

    class _Transport:
        def open_session(self):
            return _Channel()

    class _Client:
        def get_transport(self):
            return _Transport()

    cancel = threading.Event()

    def _sleep(dt):
        sleeps.append(dt)
        if len(sleeps) >= 2:
            cancel.set()

    import utils.ssh_ide_debug as ide

    real_sleep = ide.time.sleep
    ide.time.sleep = _sleep
    try:
        t0 = time.monotonic()
        code = _exec_argv(_Client(), ["true"], cwd="/tmp", timeout_sec=0, cancel=cancel)
        elapsed = time.monotonic() - t0
    finally:
        ide.time.sleep = real_sleep
    assert code == -1
    assert sleeps, "expected poll sleep"
    assert elapsed < 1.0


def test_try_handle_ide_run_debug_defers_to_runmanager(tmp_path, monkeypatch):
    """R198: debug is not refused in try_handle — RunManager owns the path."""
    from utils import ssh_project_runtime as rt

    binding, script = _binding(tmp_path)
    monkeypatch.setattr(rt, "get_loaded_project_binding", lambda: binding)
    assert rt.try_handle_ide_run(str(script), kind="debug") is False
    assert rt.try_handle_ide_run(str(script), kind="profile") is True


def test_start_ssh_ide_debug_uses_fake_tunnel(tmp_path, monkeypatch):
    """Contract: uploads + Fake tunnel + exec argv without network."""
    from utils import ssh_ide_debug as ide

    binding, script = _binding(tmp_path)
    uploads: list[tuple[str, str]] = []
    execs: list[tuple] = []
    finished: list[tuple] = []

    class FakeSftp:
        def makedirs(self, path, *, mode=0o755):
            del path, mode

        def write_bytes(self, remote_path, data):
            uploads.append((remote_path, len(data)))

        def close(self):
            return None

    class FakeWrapper:
        def __init__(self):
            self.procuuid = "puuid"

            class _Sig:
                def emit(self, *args):
                    finished.append(args)

            self.sigFinished = _Sig()

    class _Dbg:
        reportExceptions = True
        traceInterpreter = False

    class _Settings:
        def getDebuggerSettings(self):
            return _Dbg()

    monkeypatch.setattr(ide, "require_paramiko", lambda: object())
    monkeypatch.setattr(ide, "resolve_ssh_job_limits", lambda: (0.0, 0))
    monkeypatch.setattr(ide, "profile_from_binding", lambda b: b)
    monkeypatch.setattr(ide, "load_ssh_password", lambda _id: "")
    import utils.ssh_remote as ssh_remote

    monkeypatch.setattr(ssh_remote, "connect_paramiko_sftp", lambda *a, **k: FakeSftp())
    monkeypatch.setattr(ide, "open_paramiko_ssh_client", lambda *a, **k: (object(), binding))
    monkeypatch.setattr(
        ide,
        "_exec_argv",
        lambda client, argv, cwd, timeout_sec, cancel=None: execs.append((argv, cwd)) or 0,
    )
    import utils.diskvaluesrelay as dvr
    import utils.settings as settings_mod

    monkeypatch.setattr(dvr, "getRunParameters", lambda _p: {"arguments": "", "redirected": True})
    monkeypatch.setattr(settings_mod, "Settings", _Settings)

    fake_tunnel = ide.FakeReverseTunnel()
    wrapper = FakeWrapper()
    plan = ide.start_ssh_ide_debug_session(
        binding,
        str(script),
        wrapper,
        5555,
        tunnel_factory=lambda _c: fake_tunnel,
    )
    for _ in range(100):
        if fake_tunnel.opened and execs and finished:
            break
        time.sleep(0.05)
    assert plan.procuuid == "puuid"
    assert fake_tunnel.opened
    assert fake_tunnel.opened[0].remote_port == 5555
    assert uploads, "client/script uploads expected"
    assert execs, "remote exec expected"
    argv, cwd = execs[0]
    assert "127.0.0.1" in argv
    assert "5555" in argv
    assert finished, "sigFinished should fire"
    assert fake_tunnel.closed == 1
