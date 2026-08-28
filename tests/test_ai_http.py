# -*- coding: utf-8 -*-
"""HTTP AI backends with injectable urllib opener (no real network)."""

from __future__ import annotations

import io
import json
from typing import Any

import pytest
from core.ai_config import PROVIDER_ANTHROPIC, PROVIDER_OLLAMA, PROVIDER_OPENAI, AiConfig
from core.ai_context import build_ai_context_from_source
from core.ai_http import (
    AiBackendConfigError,
    AiHttpCancelled,
    AiHttpError,
    HttpChatBackend,
    assert_trusted_base_url,
)

_SRC = "def target(x):\n    return x + 1\n"


class _FakeResponse:
    def __init__(self, payload: dict[str, Any] | bytes, status: int = 200) -> None:
        if isinstance(payload, (bytes, bytearray)):
            self._raw = bytes(payload)
        else:
            self._raw = json.dumps(payload).encode("utf-8")
        self._offset = 0
        self.status = status

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            chunk = self._raw[self._offset :]
            self._offset = len(self._raw)
            return chunk
        if self._offset >= len(self._raw):
            return b""
        end = self._offset + size
        chunk = self._raw[self._offset : end]
        self._offset = end
        return chunk

    def getcode(self) -> int:
        return self.status

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def test_http_backend_requires_key_for_openai() -> None:
    cfg = AiConfig(provider=PROVIDER_OPENAI, model="gpt-4o-mini")
    with pytest.raises(AiBackendConfigError):
        HttpChatBackend(cfg, api_key="")


def test_openai_compatible_explain(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_open(request: Any, timeout: float = 0) -> _FakeResponse:
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _FakeResponse({"choices": [{"message": {"role": "assistant", "content": "target adds one"}}]})

    cfg = AiConfig(
        provider=PROVIDER_OPENAI,
        model="gpt-4o-mini",
        base_url="https://api.openai.com/v1",
    )
    backend = HttpChatBackend(cfg, api_key="sk-test", opener=fake_open)
    pack = build_ai_context_from_source(_SRC, "target", file="m.py")
    text = backend.explain(pack)
    assert text == "target adds one"
    assert backend.name == "http-openai"
    assert captured["url"].endswith("/chat/completions")
    assert any(k.lower() == "authorization" and "sk-test" in v for k, v in captured["headers"].items())
    assert captured["body"]["model"] == "gpt-4o-mini"


def test_anthropic_suggest() -> None:
    def fake_open(request: Any, timeout: float = 0) -> _FakeResponse:
        assert request.full_url.endswith("/v1/messages")
        headers = {k.lower(): v for k, v in request.header_items()}
        assert headers.get("x-api-key") == "anth-key"
        return _FakeResponse({"content": [{"type": "text", "text": "Keep it simple"}]})

    cfg = AiConfig(
        provider=PROVIDER_ANTHROPIC,
        model="claude-3-5-haiku-latest",
        base_url="https://api.anthropic.com",
    )
    backend = HttpChatBackend(cfg, api_key="anth-key", opener=fake_open)
    pack = build_ai_context_from_source(_SRC, "target", file="m.py")
    assert backend.suggest(pack) == "Keep it simple"


def test_http_error_surface() -> None:
    import urllib.error

    def fake_open(request: Any, timeout: float = 0) -> Any:
        raise urllib.error.HTTPError(
            request.full_url,
            401,
            "Unauthorized",
            hdrs=None,
            fp=io.BytesIO(b'{"error":"bad key"}'),
        )

    cfg = AiConfig(provider=PROVIDER_OPENAI, model="gpt-4o-mini")
    backend = HttpChatBackend(cfg, api_key="bad", opener=fake_open)
    pack = build_ai_context_from_source(_SRC, "target", file="m.py")
    with pytest.raises(AiHttpError) as excinfo:
        backend.explain(pack)
    assert "401" in str(excinfo.value)


def test_r192_rejects_untrusted_base_url() -> None:
    cfg = AiConfig(
        provider=PROVIDER_OPENAI,
        model="gpt-4o-mini",
        base_url="https://evil.example/v1",
    )
    with pytest.raises(AiBackendConfigError, match="trust allowlist"):
        HttpChatBackend(cfg, api_key="sk-test", environ={})


def test_r192_rejects_cleartext_non_loopback() -> None:
    with pytest.raises(AiBackendConfigError, match="cleartext"):
        assert_trusted_base_url(PROVIDER_OPENAI, "http://api.openai.com/v1", environ={})


def test_r192_allowlist_env_permits_custom_host() -> None:
    cfg = AiConfig(
        provider=PROVIDER_OPENAI,
        model="gpt-4o-mini",
        base_url="https://ai.corp.example/v1",
    )

    def fake_open(request: Any, timeout: float = 0) -> _FakeResponse:
        return _FakeResponse({"choices": [{"message": {"content": "ok"}}]})

    backend = HttpChatBackend(
        cfg,
        api_key="sk",
        opener=fake_open,
        environ={"CDM_AI_BASE_URL_ALLOWLIST": "ai.corp.example"},
    )
    pack = build_ai_context_from_source(_SRC, "target", file="m.py")
    assert backend.explain(pack) == "ok"


def test_r192_ollama_loopback_ok() -> None:
    cfg = AiConfig(
        provider=PROVIDER_OLLAMA,
        model="llama3.2",
        base_url="http://127.0.0.1:11434/v1",
    )

    def fake_open(request: Any, timeout: float = 0) -> _FakeResponse:
        return _FakeResponse({"choices": [{"message": {"content": "local"}}]})

    backend = HttpChatBackend(cfg, opener=fake_open, environ={})
    pack = build_ai_context_from_source(_SRC, "target", file="m.py")
    assert backend.explain(pack) == "local"


def test_r192_response_byte_budget() -> None:
    huge = {"choices": [{"message": {"content": "x" * 200}}]}

    def fake_open(request: Any, timeout: float = 0) -> _FakeResponse:
        return _FakeResponse(huge)

    cfg = AiConfig(provider=PROVIDER_OPENAI, model="gpt-4o-mini")
    backend = HttpChatBackend(cfg, api_key="sk", opener=fake_open, max_response_bytes=32)
    pack = build_ai_context_from_source(_SRC, "target", file="m.py")
    with pytest.raises(AiHttpError, match="byte budget"):
        backend.explain(pack)


def test_r192_cancel_during_read() -> None:
    payload = {"choices": [{"message": {"content": "never"}}]}
    calls = {"n": 0}

    def fake_open(request: Any, timeout: float = 0) -> _FakeResponse:
        return _FakeResponse(payload)

    def should_cancel() -> bool:
        calls["n"] += 1
        return calls["n"] > 1

    cfg = AiConfig(provider=PROVIDER_OPENAI, model="gpt-4o-mini")
    backend = HttpChatBackend(
        cfg,
        api_key="sk",
        opener=fake_open,
        should_cancel=should_cancel,
        max_response_bytes=1024,
    )
    pack = build_ai_context_from_source(_SRC, "target", file="m.py")
    with pytest.raises(AiHttpCancelled):
        backend.explain(pack)
