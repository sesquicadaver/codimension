# -*- coding: utf-8 -*-
"""AI provider config + API key storage (no network)."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest
from core.ai_config import (
    PROVIDER_OFFLINE,
    PROVIDER_OPENAI,
    AiConfig,
    clear_ai_api_key,
    describe_ai_provider_settings,
    get_ai_api_key,
    has_ai_api_key,
    load_ai_config,
    save_ai_config,
    store_ai_api_key,
)


def test_default_config_is_offline(tmp_path: Path) -> None:
    cfg = load_ai_config(home=str(tmp_path))
    assert cfg.provider == PROVIDER_OFFLINE
    assert cfg.requires_api_key() is False


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    save_ai_config(
        AiConfig(provider=PROVIDER_OPENAI, model="gpt-4o-mini", base_url="https://api.openai.com/v1"),
        home=str(tmp_path),
    )
    cfg = load_ai_config(home=str(tmp_path))
    assert cfg.provider == PROVIDER_OPENAI
    assert cfg.model == "gpt-4o-mini"
    path = tmp_path / ".codimension3" / "ai_settings.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "api_key" not in raw
    assert "token" not in json.dumps(raw).lower()


def test_api_key_file_fallback_mode_0600(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("core.ai_config._keyring_set", lambda *_a, **_k: False)
    monkeypatch.setattr("core.ai_config._keyring_get", lambda *_a, **_k: None)
    monkeypatch.setattr("core.ai_config._keyring_delete", lambda *_a, **_k: None)

    backend = store_ai_api_key(PROVIDER_OPENAI, "sk-test-secret", home=str(tmp_path))
    assert backend == "file"
    token_path = tmp_path / ".codimension3" / "ai_api_key"
    assert token_path.is_file()
    mode = stat.S_IMODE(os.stat(token_path).st_mode)
    assert mode == 0o600
    assert get_ai_api_key(PROVIDER_OPENAI, home=str(tmp_path)) == "sk-test-secret"
    assert has_ai_api_key(PROVIDER_OPENAI, home=str(tmp_path)) is True
    # settings JSON must not contain the secret
    save_ai_config(AiConfig(provider=PROVIDER_OPENAI, model="m"), home=str(tmp_path))
    settings_text = (tmp_path / ".codimension3" / "ai_settings.json").read_text(encoding="utf-8")
    assert "sk-test-secret" not in settings_text

    clear_ai_api_key(PROVIDER_OPENAI, home=str(tmp_path))
    assert get_ai_api_key(PROVIDER_OPENAI, home=str(tmp_path)) is None
    assert not token_path.is_file()


def test_describe_never_includes_raw_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("core.ai_config._keyring_set", lambda *_a, **_k: False)
    monkeypatch.setattr("core.ai_config._keyring_get", lambda *_a, **_k: None)
    monkeypatch.setattr("core.ai_config._keyring_delete", lambda *_a, **_k: None)
    save_ai_config(AiConfig(provider=PROVIDER_OPENAI, model="gpt-4o-mini"), home=str(tmp_path))
    store_ai_api_key(PROVIDER_OPENAI, "sk-never-echo", home=str(tmp_path))
    snap = describe_ai_provider_settings(home=str(tmp_path))
    assert snap["api_key_configured"] is True
    assert "sk-never-echo" not in json.dumps(snap)
