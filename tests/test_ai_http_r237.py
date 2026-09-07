# -*- coding: utf-8 -*-
"""R237: AI HTTP redirect hop + final URL re-validation."""

from __future__ import annotations

from typing import Any
from urllib.request import Request

import pytest
from core.ai_config import PROVIDER_OPENAI
from core.ai_http import (
    AiBackendConfigError,
    AiUrlTrust,
    TrustedAiRedirectHandler,
    assert_trusted_ai_url,
    trusted_ai_urlopen,
)


def test_r237_redirect_handler_rejects_untrusted_hop() -> None:
    trust = AiUrlTrust(provider=PROVIDER_OPENAI, environ={})
    handler = TrustedAiRedirectHandler(trust)
    req = Request("https://api.openai.com/v1/chat/completions")
    with pytest.raises(AiBackendConfigError, match="trust allowlist"):
        handler.redirect_request(
            req,
            None,
            302,
            "Found",
            {},
            "https://evil.example/v1/chat/completions",
        )


def test_r237_redirect_handler_rejects_http_downgrade() -> None:
    trust = AiUrlTrust(provider=PROVIDER_OPENAI, environ={})
    handler = TrustedAiRedirectHandler(trust)
    req = Request("https://api.openai.com/v1/chat/completions")
    with pytest.raises(AiBackendConfigError, match="cleartext"):
        handler.redirect_request(
            req,
            None,
            302,
            "Found",
            {},
            "http://api.openai.com/v1/chat/completions",
        )


def test_r237_redirect_handler_allows_same_host_hop() -> None:
    trust = AiUrlTrust(provider=PROVIDER_OPENAI, environ={})
    handler = TrustedAiRedirectHandler(trust)
    req = Request("https://api.openai.com/v1/chat/completions")
    new = handler.redirect_request(
        req,
        None,
        302,
        "Found",
        {},
        "https://api.openai.com/v1/chat/completions?region=us",
    )
    assert new is not None
    assert "api.openai.com" in new.full_url


def test_r237_assert_trusted_ai_url_rejects_host_change() -> None:
    with pytest.raises(AiBackendConfigError, match="trust allowlist"):
        assert_trusted_ai_url(PROVIDER_OPENAI, "https://attacker.example/x", environ={})


def test_r237_trusted_urlopen_rejects_evil_final_url(monkeypatch: pytest.MonkeyPatch) -> None:
    import core.ai_http as ai_http

    closed: list[bool] = []

    class _Resp:
        def geturl(self) -> str:
            return "https://evil.example/leak"

        def close(self) -> None:
            closed.append(True)

    class _Opener:
        def open(self, req: Request, timeout: Any = None) -> _Resp:
            del req, timeout
            return _Resp()

    monkeypatch.setattr(ai_http, "build_opener", lambda *args, **kwargs: _Opener())
    trust = AiUrlTrust(provider=PROVIDER_OPENAI, environ={})
    with pytest.raises(AiBackendConfigError, match="trust allowlist"):
        trusted_ai_urlopen(
            Request("https://api.openai.com/v1/chat/completions"),
            trust=trust,
        )
    assert closed == [True]


def test_r237_trusted_urlopen_accepts_trusted_final_url(monkeypatch: pytest.MonkeyPatch) -> None:
    import core.ai_http as ai_http

    class _Resp:
        def geturl(self) -> str:
            return "https://api.openai.com/v1/chat/completions"

        def read(self, n: int = -1) -> bytes:
            del n
            return b'{"ok":true}'

        def close(self) -> None:
            return None

        def __enter__(self) -> "_Resp":
            return self

        def __exit__(self, *args: object) -> bool:
            del args
            return False

    class _Opener:
        def open(self, req: Request, timeout: Any = None) -> _Resp:
            del req, timeout
            return _Resp()

    monkeypatch.setattr(ai_http, "build_opener", lambda *args, **kwargs: _Opener())
    trust = AiUrlTrust(provider=PROVIDER_OPENAI, environ={})
    resp = trusted_ai_urlopen(
        Request("https://api.openai.com/v1/chat/completions"),
        trust=trust,
    )
    assert resp.read() == b'{"ok":true}'
