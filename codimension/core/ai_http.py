# -*- coding: utf-8 -*-
#
# codimension - HTTP chat backends for AI UI (stdlib urllib)
# Copyright (C) 2026  Codimension Team
# The license is described in the LICENSE file at the root directory.
#

"""Remote AI backends using stdlib ``urllib`` (no extra runtime deps).

Supports OpenAI-compatible chat completions, Anthropic Messages API, and
Ollama's OpenAI-compatible endpoint. Network I/O is opt-in: callers must
construct this backend after reading user config / API key.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from contextlib import AbstractContextManager
from typing import Any, Callable, Mapping, Optional
from urllib.parse import urljoin

from core.ai_config import (
    PROVIDER_ANTHROPIC,
    PROVIDER_OLLAMA,
    PROVIDER_OPENAI,
    AiConfig,
)
from core.ai_context import AiContextPack

DEFAULT_TIMEOUT_SEC = 45.0
MAX_EXCERPT_CHARS = 4000
MAX_RESPONSE_CHARS = 12000

UrlOpener = Callable[..., AbstractContextManager[Any]]


class AiBackendConfigError(RuntimeError):
    """Raised when provider settings / API key are incomplete."""


class AiHttpError(RuntimeError):
    """Raised when an HTTP AI call fails (timeout, HTTP status, parse)."""


def _pack_prompt(action: str, pack: AiContextPack) -> str:
    """Build a compact text prompt from an AI context pack."""
    excerpt = (pack.source_excerpt or "").strip()
    if len(excerpt) > MAX_EXCERPT_CHARS:
        excerpt = excerpt[: MAX_EXCERPT_CHARS - 3] + "..."
    lines = [
        f"Action: {action}",
        f"Symbol: {pack.symbol.qualname or pack.symbol.name} ({pack.symbol.kind.value})",
        f"File: {pack.symbol.file}:{pack.excerpt_begin_line}-{pack.excerpt_end_line}",
        f"Definitions: {len(pack.definitions)}; references: {len(pack.references)}; related: {len(pack.related)}",
    ]
    if pack.cfg_slice is not None:
        lines.append(
            f"CFG: root={pack.cfg_slice.root_id}; nodes={len(pack.cfg_slice.nodes)}; edges={len(pack.cfg_slice.edges)}"
        )
    if pack.notes:
        lines.append("Notes: " + "; ".join(pack.notes))
    lines.append("Source excerpt:")
    lines.append(excerpt or "(empty)")
    if action == "explain":
        lines.append("Respond with a concise explanation of what this symbol does.")
    else:
        lines.append("Respond with concise, actionable improvement suggestions.")
    return "\n".join(lines)


def _join_url(base: str, path: str) -> str:
    base = (base or "").rstrip("/") + "/"
    return urljoin(base, path.lstrip("/"))


def _http_json(
    url: str,
    payload: Mapping[str, object],
    headers: Mapping[str, str],
    *,
    timeout: float,
    opener: Optional[UrlOpener] = None,
) -> dict:
    """POST JSON and return parsed object; raise AiHttpError on failure."""
    body = json.dumps(dict(payload)).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers=dict(headers),
        method="POST",
    )
    open_fn: UrlOpener = opener if opener is not None else urllib.request.urlopen
    try:
        with open_fn(request, timeout=timeout) as response:
            raw = response.read()
            status = getattr(response, "status", None) or response.getcode()
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            detail = str(exc.reason or exc)
        raise AiHttpError(f"HTTP {exc.code} from AI provider: {detail}") from exc
    except urllib.error.URLError as exc:
        raise AiHttpError(f"Network error talking to AI provider: {exc.reason}") from exc
    except TimeoutError as exc:
        raise AiHttpError("AI provider request timed out") from exc
    if status and int(status) >= 400:
        raise AiHttpError(f"HTTP {status} from AI provider")
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AiHttpError("AI provider returned non-JSON body") from exc
    if not isinstance(parsed, dict):
        raise AiHttpError("AI provider returned unexpected JSON shape")
    return parsed


def _openai_text(parsed: Mapping[str, object]) -> str:
    choices = parsed.get("choices")
    if not isinstance(choices, list) or not choices:
        raise AiHttpError("OpenAI-compatible response missing choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise AiHttpError("OpenAI-compatible choice is not an object")
    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()[:MAX_RESPONSE_CHARS]
    text = first.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()[:MAX_RESPONSE_CHARS]
    raise AiHttpError("OpenAI-compatible response missing message content")


def _anthropic_text(parsed: Mapping[str, object]) -> str:
    content = parsed.get("content")
    if not isinstance(content, list):
        raise AiHttpError("Anthropic response missing content")
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
    if not parts:
        raise AiHttpError("Anthropic response missing text blocks")
    return "\n".join(parts)[:MAX_RESPONSE_CHARS]


class HttpChatBackend:
    """Chat-completions backend for openai / anthropic / ollama providers."""

    def __init__(
        self,
        config: AiConfig,
        *,
        api_key: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT_SEC,
        opener: Optional[UrlOpener] = None,
    ) -> None:
        self._config = config.normalized()
        self._api_key = (api_key or "").strip() or None
        self._timeout = float(timeout)
        self._opener = opener
        provider = self._config.provider
        if provider not in (PROVIDER_OPENAI, PROVIDER_ANTHROPIC, PROVIDER_OLLAMA):
            raise AiBackendConfigError(f"HttpChatBackend does not support provider {provider!r}; use offline")
        if provider in (PROVIDER_OPENAI, PROVIDER_ANTHROPIC) and not self._api_key:
            raise AiBackendConfigError(
                f"API key required for provider {provider!r}. Set it in Options → AI → AI settings…"
            )

    @property
    def name(self) -> str:
        return f"http-{self._config.provider}"

    def explain(self, pack: AiContextPack) -> str:
        """Ask the provider to explain ``pack``."""
        return self.complete(
            "You are a concise Python code assistant inside Codimension IDE.",
            _pack_prompt("explain", pack),
        )

    def suggest(self, pack: AiContextPack) -> str:
        """Ask the provider for suggestions about ``pack``."""
        return self.complete(
            "You are a concise Python code assistant inside Codimension IDE.",
            _pack_prompt("suggest", pack),
        )

    def complete(self, system: str, user: str) -> str:
        """Run a single chat completion with explicit system/user messages."""
        provider = self._config.provider
        if provider == PROVIDER_ANTHROPIC:
            # Anthropic: fold system into the API system field when supported;
            # messages API accepts top-level ``system``.
            return self._call_anthropic(user, system=system)
        return self._call_openai_compatible(user, system=system)

    def _call_openai_compatible(self, prompt: str, *, system: str = "") -> str:
        url = _join_url(self._config.base_url, "chat/completions")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        messages: list[dict[str, str]] = []
        if (system or "").strip():
            messages.append({"role": "system", "content": system.strip()})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": self._config.model,
            "messages": messages,
            "temperature": 0.2,
        }
        parsed = _http_json(
            url,
            payload,
            headers,
            timeout=self._timeout,
            opener=self._opener,
        )
        return _openai_text(parsed)

    def _call_anthropic(self, prompt: str, *, system: str = "") -> str:
        url = _join_url(self._config.base_url, "v1/messages")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-api-key": self._api_key or "",
            "anthropic-version": "2023-06-01",
        }
        payload: dict[str, object] = {
            "model": self._config.model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
        if (system or "").strip():
            payload["system"] = system.strip()
        parsed = _http_json(
            url,
            payload,
            headers,
            timeout=self._timeout,
            opener=self._opener,
        )
        return _anthropic_text(parsed)


__all__ = [
    "AiBackendConfigError",
    "AiHttpError",
    "HttpChatBackend",
]
