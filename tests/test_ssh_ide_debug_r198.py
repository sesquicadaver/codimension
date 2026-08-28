# -*- coding: utf-8 -*-
"""R198: SSH IDE debug plan / Fake tunnel / path-map contracts."""

from __future__ import annotations

import os
import sys
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
    from utils.ssh_ide_debug import FakeReverseTunnel, ReverseTunnelSpec

    tunnel = FakeReverseTunnel()
    spec = ReverseTunnelSpec(remote_port=9, local_port=9)
    tunnel.open(spec)
    tunnel.close()
    assert tunnel.opened == [spec]
    assert tunnel.closed == 1


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
    monkeypatch.setattr(
        "utils.ssh_remote.connect_paramiko_sftp",
        lambda *a, **k: FakeSftp(),
    )
    monkeypatch.setattr(ide, "open_paramiko_ssh_client", lambda *a, **k: (object(), binding))
    monkeypatch.setattr(ide, "_exec_argv", lambda client, argv, cwd, timeout_sec: execs.append((argv, cwd)) or 0)
    monkeypatch.setattr(
        "utils.diskvaluesrelay.getRunParameters",
        lambda _p: {"arguments": "", "redirected": True},
    )
    monkeypatch.setattr("utils.settings.Settings", _Settings)

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
