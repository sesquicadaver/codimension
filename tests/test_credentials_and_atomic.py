# -*- coding: utf-8 -*-
"""T040–T044 — credentials resolver, atomic writes, project schema."""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CODMENSION = ROOT / "codimension"
CDMPLUGINS = ROOT / "cdmplugins"
sys.path.insert(0, str(CODMENSION))
sys.path.insert(0, str(ROOT))


def _load_credentials(monkeypatch, tmp_path):
    """Load credentials module without importing heavy git plugin package."""
    # Minimal stubs for utils.settings
    settings_mod = types.ModuleType("utils.settings")
    settings_mod.SETTINGS_DIR = str(tmp_path) + os.sep
    sys.modules["utils.settings"] = settings_mod

    # Ensure utils.atomic_io is importable
    if "utils" not in sys.modules:
        utils_pkg = types.ModuleType("utils")
        utils_pkg.__path__ = [str(CODMENSION / "utils")]
        sys.modules["utils"] = utils_pkg

    path = CDMPLUGINS / "git" / "credentials.py"
    spec = importlib.util.spec_from_file_location("cdmplugins.git.credentials", path)
    mod = importlib.util.module_from_spec(spec)
    # Fake parent packages
    sys.modules.setdefault("cdmplugins", types.ModuleType("cdmplugins"))
    sys.modules.setdefault("cdmplugins.git", types.ModuleType("cdmplugins.git"))
    sys.modules["cdmplugins.git.credentials"] = mod
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "TOKEN_FILE", str(tmp_path / "github_token"))
    return mod


def _load_gitconfig(monkeypatch, tmp_path, cred_mod):
    settings_mod = types.ModuleType("utils.settings")
    settings_mod.SETTINGS_DIR = str(tmp_path) + os.sep
    sys.modules["utils.settings"] = settings_mod

    # Stub ui.qt for gitconfig dialog imports
    ui_pkg = types.ModuleType("ui")
    ui_pkg.__path__ = [str(CODMENSION / "ui")]
    sys.modules["ui"] = ui_pkg
    qt = types.ModuleType("ui.qt")
    for name in (
        "QDialog",
        "QDialogButtonBox",
        "QGridLayout",
        "QLabel",
        "QLineEdit",
        "QVBoxLayout",
    ):
        setattr(qt, name, type(name, (), {"Password": 0, "Ok": 1, "Cancel": 2, "__init__": lambda *a, **k: None}))
    sys.modules["ui.qt"] = qt

    sys.modules["cdmplugins.git.credentials"] = cred_mod
    path = CDMPLUGINS / "git" / "gitconfig.py"
    spec = importlib.util.spec_from_file_location("cdmplugins.git.gitconfig", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cdmplugins.git.gitconfig"] = mod
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "CONFIG_FILE", str(tmp_path / "git.plugin.conf"))
    return mod


def test_atomic_write_text_mode(tmp_path):
    from utils.atomic_io import atomic_write_text

    path = tmp_path / "secret.conf"
    atomic_write_text(str(path), "token=abc\n", mode=0o600)
    assert path.read_text(encoding="utf-8") == "token=abc\n"
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600


def test_resolve_github_token_order(monkeypatch, tmp_path):
    cred = _load_credentials(monkeypatch, tmp_path)

    token, source = cred.resolve_github_token(
        "gh",
        gh_getter=lambda _p: None,
        keyring_getter=lambda: None,
        file_getter=lambda: "file-token",
    )
    assert token == "file-token"
    assert source == "file"

    token, source = cred.resolve_github_token(
        "gh",
        gh_getter=lambda _p: "gh-token",
        keyring_getter=lambda: "kr-token",
        file_getter=lambda: "file-token",
    )
    assert token == "gh-token"
    assert source == "gh"

    token, source = cred.resolve_github_token(
        "gh",
        gh_getter=lambda _p: None,
        keyring_getter=lambda: "kr-token",
        file_getter=lambda: "file-token",
    )
    assert token == "kr-token"
    assert source == "keyring"


def test_store_github_token_file_fallback(monkeypatch, tmp_path):
    cred = _load_credentials(monkeypatch, tmp_path)
    monkeypatch.setattr(cred, "_keyring_set", lambda _t: False)
    backend = cred.store_github_token("secret-pat")
    assert backend == "file"
    token_path = Path(cred.TOKEN_FILE)
    assert token_path.read_text(encoding="utf-8").strip() == "secret-pat"
    assert stat.S_IMODE(token_path.stat().st_mode) == 0o600


def test_plaintext_token_scrubbed_from_conf(monkeypatch, tmp_path):
    """Legacy github_token in conf is migrated and removed (T040)."""
    cred = _load_credentials(monkeypatch, tmp_path)
    gitconfig = _load_gitconfig(monkeypatch, tmp_path, cred)
    conf = Path(gitconfig.CONFIG_FILE)
    conf.write_text(
        "[general]\ngit_path = git\ngh_path = gh\ndefault_remote = origin\n"
        "github_token = legacy-pat\ngithub_username = u\ngithub_repo_override = \n",
        encoding="utf-8",
    )
    stored = {}

    def _store(token):
        stored["token"] = token
        return "file"

    monkeypatch.setattr(gitconfig, "store_github_token", _store)
    monkeypatch.setattr(gitconfig, "has_stored_github_token", lambda: bool(stored))

    cfg = gitconfig.load_config()
    text = conf.read_text(encoding="utf-8")
    assert "github_token" not in text
    assert stored.get("token") == "legacy-pat"
    assert cfg["github_token_configured"] is True


def test_project_schema_rejects_bad_types():
    from utils.project_schema import ProjectSchemaError, validate_project_props

    with pytest.raises(ProjectSchemaError):
        validate_project_props(["not", "a", "dict"])
    with pytest.raises(ProjectSchemaError):
        validate_project_props({"uuid": 123})
    with pytest.raises(ProjectSchemaError):
        validate_project_props({"importdirs": "oops"})
    with pytest.raises(ProjectSchemaError):
        validate_project_props({"uuid": "abc"})
    ok = validate_project_props({"uuid": "11111111-1111-1111-1111-111111111111", "importdirs": ["src"]})
    assert ok["uuid"] == "11111111-1111-1111-1111-111111111111"


def test_atomic_project_save_roundtrip(tmp_path):
    """saveProject uses atomic_write_text (crash-safe pattern)."""
    from utils.atomic_io import atomic_write_text
    from utils.project_schema import validate_project_props

    path = tmp_path / "demo.cdm3"
    props = {
        "uuid": "11111111-1111-1111-1111-111111111111",
        "scriptname": "",
        "mddocfile": "",
        "creationdate": "",
        "author": "",
        "license": "",
        "copyright": "",
        "version": "0.0.1",
        "email": "",
        "description": "",
        "importdirs": [],
        "excludeFromAnalysis": [],
        "encoding": "",
        "pythoninterpreter": "",
    }
    atomic_write_text(str(path), json.dumps(props, indent=4) + "\n")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    validate_project_props(loaded)
    assert loaded["uuid"] == props["uuid"]
