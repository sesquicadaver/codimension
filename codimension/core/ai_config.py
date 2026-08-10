# -*- coding: utf-8 -*-
#
# codimension - AI provider / API key configuration (Qt-free)
# Copyright (C) 2026  Codimension Team
# The license is described in the LICENSE file at the root directory.
#

"""Persist AI provider selection and API keys outside the project tree.

- Non-secret settings: ``~/.codimension3/ai_settings.json``
- Secrets: OS keyring (preferred) or ``~/.codimension3/ai_api_key`` mode ``0600``

Default provider remains ``offline`` (no network, no key) so existing MVP behaviour
is unchanged until the user explicitly selects a remote provider.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from typing import Mapping, Optional

CONFIG_DIR_NAME = ".codimension3"
SETTINGS_FILENAME = "ai_settings.json"
TOKEN_FILENAME = "ai_api_key"
TOKEN_FILE_MODE = 0o600

KEYRING_SERVICE = "codimension-ai"

PROVIDER_OFFLINE = "offline"
PROVIDER_OPENAI = "openai"
PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_OLLAMA = "ollama"

KNOWN_PROVIDERS: tuple[str, ...] = (
    PROVIDER_OFFLINE,
    PROVIDER_OPENAI,
    PROVIDER_ANTHROPIC,
    PROVIDER_OLLAMA,
)

PROVIDER_LABELS: Mapping[str, str] = {
    PROVIDER_OFFLINE: "Offline (local summary, no API)",
    PROVIDER_OPENAI: "OpenAI",
    PROVIDER_ANTHROPIC: "Anthropic",
    PROVIDER_OLLAMA: "Ollama (local HTTP)",
}

DEFAULT_MODELS: Mapping[str, str] = {
    PROVIDER_OFFLINE: "",
    PROVIDER_OPENAI: "gpt-4o-mini",
    PROVIDER_ANTHROPIC: "claude-3-5-haiku-latest",
    PROVIDER_OLLAMA: "llama3.2",
}

DEFAULT_BASE_URLS: Mapping[str, str] = {
    PROVIDER_OFFLINE: "",
    PROVIDER_OPENAI: "https://api.openai.com/v1",
    PROVIDER_ANTHROPIC: "https://api.anthropic.com",
    PROVIDER_OLLAMA: "http://127.0.0.1:11434/v1",
}

_PROVIDERS_REQUIRING_KEY = frozenset({PROVIDER_OPENAI, PROVIDER_ANTHROPIC})


@dataclass(frozen=True)
class AiConfig:
    """Non-secret AI settings snapshot."""

    provider: str = PROVIDER_OFFLINE
    model: str = ""
    base_url: str = ""

    def normalized(self) -> "AiConfig":
        """Return a copy with known provider and defaults filled."""
        provider = self.provider if self.provider in KNOWN_PROVIDERS else PROVIDER_OFFLINE
        model = (self.model or "").strip() or DEFAULT_MODELS.get(provider, "")
        base_url = (self.base_url or "").strip() or DEFAULT_BASE_URLS.get(provider, "")
        return AiConfig(provider=provider, model=model, base_url=base_url)

    def requires_api_key(self) -> bool:
        """True when a remote provider needs a stored API key."""
        return self.normalized().provider in _PROVIDERS_REQUIRING_KEY

    def to_dict(self) -> dict[str, str]:
        """JSON-serializable mapping (never includes secrets)."""
        cfg = self.normalized()
        return {
            "provider": cfg.provider,
            "model": cfg.model,
            "base_url": cfg.base_url,
        }


def default_ai_config_dir(home: Optional[str] = None) -> str:
    """Return ``~/.codimension3`` (or ``home/.codimension3``)."""
    base = os.path.expanduser(home if home is not None else "~")
    return os.path.join(base, CONFIG_DIR_NAME)


def default_ai_settings_path(home: Optional[str] = None) -> str:
    """Path to the non-secret AI settings JSON file."""
    return os.path.join(default_ai_config_dir(home), SETTINGS_FILENAME)


def default_ai_token_path(home: Optional[str] = None) -> str:
    """Path to the fallback API-key file (mode 0600)."""
    return os.path.join(default_ai_config_dir(home), TOKEN_FILENAME)


def _atomic_write_json(path: str, payload: Mapping[str, object]) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, mode=0o755, exist_ok=True)
    text = json.dumps(dict(payload), indent=2, sort_keys=True) + "\n"
    fd, tmp_path = tempfile.mkstemp(prefix=".cdm-ai-", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            if os.path.isfile(tmp_path):
                os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_ai_config(*, path: Optional[str] = None, home: Optional[str] = None) -> AiConfig:
    """Load AI settings; missing/invalid file → offline defaults."""
    settings_path = path if path is not None else default_ai_settings_path(home)
    if not os.path.isfile(settings_path):
        return AiConfig().normalized()
    try:
        with open(settings_path, encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError):
        return AiConfig().normalized()
    if not isinstance(raw, dict):
        return AiConfig().normalized()
    return AiConfig(
        provider=str(raw.get("provider") or PROVIDER_OFFLINE),
        model=str(raw.get("model") or ""),
        base_url=str(raw.get("base_url") or ""),
    ).normalized()


def save_ai_config(config: AiConfig, *, path: Optional[str] = None, home: Optional[str] = None) -> None:
    """Persist non-secret AI settings."""
    settings_path = path if path is not None else default_ai_settings_path(home)
    _atomic_write_json(settings_path, config.normalized().to_dict())


def _keyring_username(provider: str) -> str:
    return f"api-key:{provider}"


def _keyring_get(provider: str) -> str | None:
    try:
        import keyring
    except ImportError:
        return None
    try:
        value = keyring.get_password(KEYRING_SERVICE, _keyring_username(provider))
        return value.strip() if value else None
    except Exception as exc:
        logging.debug("AI keyring get failed: %s", exc)
        return None


def _keyring_set(provider: str, token: str) -> bool:
    try:
        import keyring
    except ImportError:
        return False
    try:
        keyring.set_password(KEYRING_SERVICE, _keyring_username(provider), token)
        return True
    except Exception as exc:
        logging.debug("AI keyring set failed: %s", exc)
        return False


def _keyring_delete(provider: str) -> None:
    try:
        import keyring
    except ImportError:
        return
    try:
        keyring.delete_password(KEYRING_SERVICE, _keyring_username(provider))
    except Exception:
        pass


def _file_payload_get(path: str, provider: str) -> str | None:
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(raw, dict):
        return None
    value = raw.get(provider)
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _file_payload_set(path: str, provider: str, token: str) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, mode=0o755, exist_ok=True)
    data: dict[str, str] = {}
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as handle:
                raw = json.load(handle)
            if isinstance(raw, dict):
                data = {str(k): str(v) for k, v in raw.items() if isinstance(v, str)}
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError):
            data = {}
    data[provider] = token
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    fd, tmp_path = tempfile.mkstemp(prefix=".cdm-ai-key-", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_path, TOKEN_FILE_MODE)
        os.replace(tmp_path, path)
        try:
            os.chmod(path, TOKEN_FILE_MODE)
        except OSError:
            pass
    except Exception:
        try:
            if os.path.isfile(tmp_path):
                os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _file_payload_delete(path: str, provider: str) -> None:
    if not os.path.isfile(path):
        return
    try:
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError):
        return
    if not isinstance(raw, dict) or provider not in raw:
        return
    data = {str(k): str(v) for k, v in raw.items() if isinstance(v, str) and k != provider}
    if not data:
        try:
            os.unlink(path)
        except OSError:
            pass
        return
    directory = os.path.dirname(path) or "."
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    fd, tmp_path = tempfile.mkstemp(prefix=".cdm-ai-key-", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_path, TOKEN_FILE_MODE)
        os.replace(tmp_path, path)
        try:
            os.chmod(path, TOKEN_FILE_MODE)
        except OSError:
            pass
    except Exception:
        try:
            if os.path.isfile(tmp_path):
                os.unlink(tmp_path)
        except OSError:
            pass
        raise


def get_ai_api_key(
    provider: str,
    *,
    home: Optional[str] = None,
    token_path: Optional[str] = None,
) -> str | None:
    """Return stored API key for ``provider`` (keyring, then file)."""
    provider = (provider or "").strip() or PROVIDER_OFFLINE
    if provider == PROVIDER_OFFLINE:
        return None
    token = _keyring_get(provider)
    if token:
        return token
    path = token_path if token_path is not None else default_ai_token_path(home)
    return _file_payload_get(path, provider)


def store_ai_api_key(
    provider: str,
    token: str,
    *,
    home: Optional[str] = None,
    token_path: Optional[str] = None,
) -> str:
    """Persist API key. Returns backend name: keyring|file|cleared."""
    provider = (provider or "").strip() or PROVIDER_OFFLINE
    token = (token or "").strip()
    if provider == PROVIDER_OFFLINE or not token:
        clear_ai_api_key(provider, home=home, token_path=token_path)
        return "cleared"
    if _keyring_set(provider, token):
        path = token_path if token_path is not None else default_ai_token_path(home)
        _file_payload_delete(path, provider)
        return "keyring"
    path = token_path if token_path is not None else default_ai_token_path(home)
    _file_payload_set(path, provider, token)
    return "file"


def clear_ai_api_key(
    provider: str,
    *,
    home: Optional[str] = None,
    token_path: Optional[str] = None,
) -> None:
    """Remove stored API key for ``provider`` from keyring and file."""
    provider = (provider or "").strip() or PROVIDER_OFFLINE
    if provider == PROVIDER_OFFLINE:
        return
    _keyring_delete(provider)
    path = token_path if token_path is not None else default_ai_token_path(home)
    _file_payload_delete(path, provider)


def has_ai_api_key(
    provider: str,
    *,
    home: Optional[str] = None,
    token_path: Optional[str] = None,
) -> bool:
    """True when a non-empty key is stored for ``provider``."""
    return bool(get_ai_api_key(provider, home=home, token_path=token_path))


def describe_ai_provider_settings(
    *,
    home: Optional[str] = None,
    settings_path: Optional[str] = None,
    token_path: Optional[str] = None,
) -> dict[str, object]:
    """UI/diagnostics snapshot (never includes the raw API key)."""
    cfg = load_ai_config(path=settings_path, home=home)
    key_ok = has_ai_api_key(cfg.provider, home=home, token_path=token_path)
    return {
        "provider": cfg.provider,
        "provider_label": PROVIDER_LABELS.get(cfg.provider, cfg.provider),
        "model": cfg.model,
        "base_url": cfg.base_url,
        "requires_api_key": cfg.requires_api_key(),
        "api_key_configured": key_ok,
        "settings_path": settings_path or default_ai_settings_path(home),
    }


__all__ = [
    "DEFAULT_BASE_URLS",
    "DEFAULT_MODELS",
    "KNOWN_PROVIDERS",
    "PROVIDER_ANTHROPIC",
    "PROVIDER_LABELS",
    "PROVIDER_OFFLINE",
    "PROVIDER_OLLAMA",
    "PROVIDER_OPENAI",
    "AiConfig",
    "clear_ai_api_key",
    "default_ai_config_dir",
    "default_ai_settings_path",
    "default_ai_token_path",
    "describe_ai_provider_settings",
    "get_ai_api_key",
    "has_ai_api_key",
    "load_ai_config",
    "save_ai_config",
    "store_ai_api_key",
]
