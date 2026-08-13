# -*- coding: utf-8 -*-
"""SSH remote project open/create (Fake SFTP; no network)."""

from __future__ import annotations

import json
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
    pkg_path = getattr(mod, "__path__", None)
    if not pkg_path:
        return False
    try:
        first = os.path.abspath(list(pkg_path)[0]).replace("\\", "/")
    except Exception:
        return False
    return "/codimension/" in first


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


def test_profile_roundtrip(tmp_path):
    from utils.ssh_remote import SshHostProfile, load_host_profiles, upsert_host_profile

    settings = str(tmp_path)
    profile = SshHostProfile(id="", host="dev.example", port=2222, user="alice", auth="key")
    saved = upsert_host_profile(profile, settings)
    assert saved.id
    assert "password" not in saved.to_dict()
    loaded = load_host_profiles(settings)
    assert len(loaded) == 1
    assert loaded[0].host == "dev.example"
    assert loaded[0].port == 2222


def test_password_file_fallback(tmp_path, monkeypatch):
    import types

    from utils.ssh_remote import load_ssh_password, password_file_path, store_ssh_password

    settings = str(tmp_path)

    def boom(*_a, **_k):
        raise RuntimeError("no keyring")

    fake = types.ModuleType("keyring")
    fake.set_password = boom
    fake.get_password = boom
    monkeypatch.setitem(sys.modules, "keyring", fake)

    store_ssh_password("p1", "secret", settings)
    path = password_file_path("p1", settings)
    assert os.path.isfile(path)
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"
    assert load_ssh_password("p1", settings) == "secret"


def test_fake_open_and_create(tmp_path):
    from utils.ssh_remote import (
        FakeSftpSession,
        SshHostProfile,
        create_remote_project,
        default_cdm3_json,
        open_remote_project,
        read_binding,
    )

    settings = str(tmp_path / "settings")
    os.makedirs(settings)
    body = default_cdm3_json("demo")
    props = json.loads(body)
    assert props["uuid"]

    session = FakeSftpSession(
        {
            "home": {
                "alice": {
                    "demo": {
                        "demo.cdm3": body,
                        "main.py": "print('hi')\n",
                        ".venv": {"lib": {"x.py": "# skip\n"}},
                    }
                }
            }
        }
    )
    profile = SshHostProfile(id="alice-dev", host="dev", user="alice", auth="key").normalized()
    binding = open_remote_project(session, profile, "/home/alice/demo", settings_dir=settings)
    assert os.path.isfile(binding.local_cdm3)
    assert os.path.isfile(os.path.join(binding.local_root, "main.py"))
    assert not os.path.exists(os.path.join(binding.local_root, ".venv"))
    assert read_binding(binding.local_root) is not None

    create_session = FakeSftpSession()
    create_session.makedirs("/projects")
    created = create_remote_project(
        create_session,
        profile,
        "/projects",
        "fresh",
        cdm3_body=default_cdm3_json("fresh"),
        settings_dir=settings,
    )
    assert create_session.isfile("/projects/fresh/fresh.cdm3")
    assert os.path.isfile(created.local_cdm3)
    assert created.remote_root == "/projects/fresh"


def test_remote_relpath_and_cdm3_props():
    import json

    from utils.ssh_remote import cdm3_json_from_props, remote_relpath

    assert remote_relpath("/home/u/proj", "/home/u/proj/main.py") == "main.py"
    assert remote_relpath("/home/u/proj", "/home/u/proj") == "."
    assert remote_relpath("/home/u/proj", "/other/x.py") == "/other/x.py"
    body = cdm3_json_from_props(
        {
            "uuid": "",
            "scriptname": "main.py",
            "author": "A",
            "description": "d",
            "pythoninterpreter": "venv/bin/python",
        }
    )
    props = json.loads(body)
    assert props["scriptname"] == "main.py"
    assert props["uuid"]
    assert props["pythoninterpreter"] == "venv/bin/python"


def test_download_optional_limits(tmp_path):
    from utils.ssh_remote import FakeSftpSession, download_remote_tree

    session = FakeSftpSession({"a.txt": "x" * 100, "b.txt": "y" * 100})
    # Default: unlimited — both files land in the cache.
    assert download_remote_tree(session, "/", str(tmp_path / "full")) == 2
    with pytest.raises(RuntimeError, match="size limit"):
        download_remote_tree(session, "/", str(tmp_path / "capped"), max_files=10, max_bytes=50)


def test_download_env_limits(tmp_path, monkeypatch):
    from utils.ssh_remote import FakeSftpSession, download_remote_tree

    monkeypatch.setenv("CDM_SSH_MAX_FILES", "1")
    session = FakeSftpSession({"a.txt": "aa", "b.txt": "bb"})
    with pytest.raises(RuntimeError, match="file count limit"):
        download_remote_tree(session, "/", str(tmp_path / "env"))


def test_find_remote_cdm3():
    from utils.ssh_remote import FakeSftpSession, find_remote_cdm3

    session = FakeSftpSession({"proj": {"app.cdm3": "{}", "main.py": "x"}})
    assert find_remote_cdm3(session, "/proj") == "/proj/app.cdm3"
    assert find_remote_cdm3(session, "/proj/app.cdm3") == "/proj/app.cdm3"
    with pytest.raises(FileNotFoundError):
        find_remote_cdm3(FakeSftpSession({"empty": {}}), "/empty")


def test_require_paramiko_message():
    from utils import ssh_remote as mod

    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "paramiko" or name.startswith("paramiko."):
            raise ImportError("nope")
        return real_import(name, *args, **kwargs)

    import builtins

    builtins.__import__ = fake_import
    try:
        with pytest.raises(RuntimeError, match="paramiko"):
            mod.require_paramiko()
    finally:
        builtins.__import__ = real_import
