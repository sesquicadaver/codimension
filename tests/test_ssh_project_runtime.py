# -*- coding: utf-8 -*-
"""SSH remote runtime: path map + upload helpers (no network)."""

from __future__ import annotations

import os
import sys
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


def test_map_local_to_remote(tmp_path):
    from utils.ssh_project_runtime import is_under_binding, map_local_to_remote
    from utils.ssh_remote import RemoteProjectBinding

    local_root = tmp_path / "cache"
    local_root.mkdir()
    script = local_root / "pkg" / "main.py"
    script.parent.mkdir()
    script.write_text("print(1)\n", encoding="utf-8")

    binding = RemoteProjectBinding(
        profile_id="p1",
        host="h",
        port=22,
        user="u",
        auth="key",
        identity_file="",
        remote_root="/home/u/proj",
        remote_cdm3="/home/u/proj/proj.cdm3",
        local_root=str(local_root),
        local_cdm3=str(local_root / "proj.cdm3"),
    )
    assert map_local_to_remote(binding, str(script)) == "/home/u/proj/pkg/main.py"
    assert is_under_binding(binding, str(script))
    assert not is_under_binding(binding, str(tmp_path / "other.py"))


def test_upload_via_fake(tmp_path):
    from utils.ssh_project_runtime import map_local_to_remote
    from utils.ssh_remote import FakeSftpSession, RemoteProjectBinding, upload_file

    local_root = tmp_path / "cache"
    local_root.mkdir()
    local = local_root / "a.py"
    local.write_text("x=1\n", encoding="utf-8")
    binding = RemoteProjectBinding(
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
    )
    remote = map_local_to_remote(binding, str(local))
    session = FakeSftpSession()
    session.makedirs("/r")
    upload_file(session, str(local), remote)
    assert session.read_bytes(remote) == b"x=1\n"
