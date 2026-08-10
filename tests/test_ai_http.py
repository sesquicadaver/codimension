# -*- coding: utf-8 -*-
"""HTTP AI backends with injectable urllib opener (no real network)."""

from __future__ import annotations

import io
import json
from typing import Any

import pytest
from core.ai_config import PROVIDER_ANTHROPIC, PROVIDER_OPENAI, AiConfig
from core.ai_context import build_ai_context_from_source
from core.ai_http import AiBackendConfigError, AiHttpError, HttpChatBackend

_SRC = "def target(x):\n    return x + 1\n"


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], status: int = 200) -> None:
        self._raw = json.dumps(payload).encode("utf-8")
        self.status = status

    def read(self) -> bytes:
        return self._raw

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
        return _FakeResponse(
            {
                "choices": [
                    {"message": {"role": "assistant", "content": "target adds one"}}
                ]
            }
        )

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
        return _FakeResponse(
            {"content": [{"type": "text", "text": "Keep it simple"}]}
        )

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
