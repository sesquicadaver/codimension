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
    # Default nonzero caps still allow a tiny tree.
    assert download_remote_tree(session, "/", str(tmp_path / "full")) == 2
    with pytest.raises(RuntimeError, match="size limit"):
        download_remote_tree(session, "/", str(tmp_path / "capped"), max_files=10, max_bytes=50)
    # Explicit 0 = unlimited (override R185 defaults).
    assert download_remote_tree(session, "/", str(tmp_path / "uncapped"), max_files=0, max_bytes=0) == 2


def test_download_env_limits(tmp_path, monkeypatch):
    from utils.ssh_remote import FakeSftpSession, download_remote_tree

    monkeypatch.setenv("CDM_SSH_MAX_FILES", "1")
    session = FakeSftpSession({"a.txt": "aa", "b.txt": "bb"})
    with pytest.raises(RuntimeError, match="file count limit"):
        download_remote_tree(session, "/", str(tmp_path / "env"))


def test_r185_default_limits_nonzero():
    from utils.ssh_remote import MAX_REMOTE_BYTES, MAX_REMOTE_FILES, resolve_download_limits

    assert MAX_REMOTE_FILES > 0
    assert MAX_REMOTE_BYTES > 0
    files, size = resolve_download_limits()
    assert files == MAX_REMOTE_FILES
    assert size == MAX_REMOTE_BYTES


def test_r185_reject_symlink(tmp_path):
    from utils.ssh_remote import FakeSftpSession, download_remote_tree

    session = FakeSftpSession({"ok.txt": "hi\n"})
    session.add_symlink("/escape", "/etc/passwd")
    with pytest.raises(RuntimeError, match="symlink"):
        download_remote_tree(session, "/", str(tmp_path / "out"))


def test_r185_staging_preserves_cache_on_failure(tmp_path):
    from utils.ssh_remote import (
        FakeSftpSession,
        SshHostProfile,
        default_cdm3_json,
        open_remote_project,
    )

    settings = str(tmp_path / "settings")
    os.makedirs(settings)
    body = default_cdm3_json("demo")
    session = FakeSftpSession({"home": {"alice": {"demo": {"demo.cdm3": body, "main.py": "print(1)\n"}}}})
    profile = SshHostProfile(id="alice-dev", host="dev", user="alice", auth="key").normalized()
    binding = open_remote_project(session, profile, "/home/alice/demo", settings_dir=settings)
    marker = Path(binding.local_root) / "main.py"
    assert marker.read_text(encoding="utf-8") == "print(1)\n"

    # Poison the remote tree with a symlink; re-open must fail and keep the old cache.
    session.add_symlink("/home/alice/demo/evil", "/tmp/outside")
    with pytest.raises(RuntimeError, match="symlink"):
        open_remote_project(session, profile, "/home/alice/demo", settings_dir=settings)
    assert marker.is_file()
    assert marker.read_text(encoding="utf-8") == "print(1)\n"
    # No leftover staging dirs under the profile cache parent.
    parent = Path(binding.local_root).parent
    leftovers = [p for p in parent.iterdir() if p.name.startswith(".cdm-ssh-stage-")]
    assert leftovers == []


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


def test_r183_rejects_path_like_profile_id_and_project_name(tmp_path):
    from utils.ssh_remote import (
        FakeSftpSession,
        SshHostProfile,
        create_remote_project,
        default_cdm3_json,
        remote_cache_dir,
        sanitize_remote_project_name,
        sanitize_ssh_profile_id,
    )

    for bad in ("../escape", "/abs", "a/b", "a\\b", ".", "..", ""):
        with pytest.raises(ValueError):
            sanitize_ssh_profile_id(bad)
        with pytest.raises(ValueError):
            sanitize_remote_project_name(bad)

    with pytest.raises(ValueError, match="profile id"):
        SshHostProfile(id="../evil", host="h", user="u", auth="key").normalized()

    settings = str(tmp_path / "settings")
    os.makedirs(settings)
    profile = SshHostProfile(id="safe-host", host="h", user="u", auth="key").normalized()
    cache = remote_cache_dir(profile, "/projects/demo", settings)
    assert cache.startswith(os.path.join(os.path.abspath(settings), "remote-projects"))
    assert ".." not in Path(cache).parts

    session = FakeSftpSession()
    session.makedirs("/projects")
    with pytest.raises(ValueError, match="project name"):
        create_remote_project(
            session,
            profile,
            "/projects",
            "../escape",
            cdm3_body=default_cdm3_json("x"),
            settings_dir=settings,
        )


def test_r183_rm_tree_refuses_outside_cache(tmp_path):
    from utils.ssh_remote import _rm_tree, remote_projects_root

    settings = str(tmp_path / "settings")
    cache_root = remote_projects_root(settings)
    os.makedirs(cache_root)
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "keep.txt"
    marker.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="escapes"):
        _rm_tree(str(outside), must_be_under=cache_root)
    assert marker.is_file()


def test_r184_fingerprint_normalize_and_mismatch():
    from utils.ssh_remote import (
        HostKeyFingerprintMismatch,
        normalize_host_key_fingerprint,
        ssh_host_key_fingerprint,
        verify_remote_host_key_fingerprint,
    )

    assert normalize_host_key_fingerprint("SHA256:abc+def/") == "SHA256:abc+def/"
    assert normalize_host_key_fingerprint("abc+def/==") == "SHA256:abc+def/"

    class _Key:
        def asbytes(self):
            return b"unit-test-key-bytes"

    fp = ssh_host_key_fingerprint(_Key())
    assert fp.startswith("SHA256:")

    class _Transport:
        def get_remote_server_key(self):
            return _Key()

    class _Client:
        def get_transport(self):
            return _Transport()

    assert verify_remote_host_key_fingerprint(_Client(), fp, hostname="h") == fp
    with pytest.raises(HostKeyFingerprintMismatch):
        verify_remote_host_key_fingerprint(_Client(), "SHA256:not-the-key", hostname="h")


def test_r184_profile_persists_host_key_fingerprint(tmp_path):
    from utils.ssh_remote import SshHostProfile, load_host_profiles, upsert_host_profile

    settings = str(tmp_path)
    profile = SshHostProfile(
        id="pin-host",
        host="dev.example",
        user="alice",
        auth="key",
        host_key_fingerprint="SHA256:abcdefghijklmnopqrstuvwx",
    )
    saved = upsert_host_profile(profile, settings)
    assert saved.host_key_fingerprint.startswith("SHA256:")
    loaded = load_host_profiles(settings)
    assert loaded[0].host_key_fingerprint == saved.host_key_fingerprint


def test_r184_reject_policy_raises_unknown_host_key():
    from utils.ssh_remote import UnknownHostKeyError, _reject_missing_host_key_policy, require_paramiko

    paramiko = require_paramiko()
    policy = _reject_missing_host_key_policy(paramiko)

    class _Key:
        def asbytes(self):
            return b"k"

        def get_name(self):
            return "ssh-ed25519"

    with pytest.raises(UnknownHostKeyError) as raised:
        policy.missing_host_key(None, "dev.example", _Key())
    assert raised.value.hostname == "dev.example"
    assert raised.value.fingerprint.startswith("SHA256:")
