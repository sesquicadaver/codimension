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

R192 / A220: response bodies are read in bounded chunks with an optional cancel
callback; ``base_url`` must match a trust allowlist (provider defaults + env).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from contextlib import AbstractContextManager
from typing import Any, Callable, Mapping, Optional, Sequence
from urllib.parse import urljoin, urlparse

from core.ai_config import (
    DEFAULT_BASE_URLS,
    PROVIDER_ANTHROPIC,
    PROVIDER_OLLAMA,
    PROVIDER_OPENAI,
    AiConfig,
)
from core.ai_context import AiContextPack

DEFAULT_TIMEOUT_SEC = 45.0
MAX_EXCERPT_CHARS = 4000
MAX_RESPONSE_CHARS = 12000
# Hard cap on raw HTTP body bytes (A220: no unbounded ``response.read()``).
MAX_RESPONSE_BYTES = 256 * 1024
_READ_CHUNK_BYTES = 16 * 1024

# Env: comma-separated extra trusted hosts or full base URLs (optional).
_ALLOWLIST_ENV = "CDM_AI_BASE_URL_ALLOWLIST"

UrlOpener = Callable[..., AbstractContextManager[Any]]
CancelCheck = Callable[[], bool]


class AiBackendConfigError(RuntimeError):
    """Raised when provider settings / API key are incomplete."""


class AiHttpError(RuntimeError):
    """Raised when an HTTP AI call fails (timeout, HTTP status, parse)."""


class AiHttpCancelled(AiHttpError):
    """Raised when the caller cancels an in-flight AI HTTP read."""


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


def _host_key(netloc: str) -> str:
    """Lowercase host without userinfo or port."""
    host = (netloc or "").split("@")[-1].strip().lower()
    if host.startswith("["):
        # IPv6 literal: [::1]:11434 → [::1]
        end = host.find("]")
        if end != -1:
            return host[: end + 1]
        return host
    if ":" in host:
        host = host.rsplit(":", 1)[0]
    return host


def _parse_allowlist_entries(raw: str | None) -> set[str]:
    """Parse comma-separated hosts or URLs into normalized host keys."""
    hosts: set[str] = set()
    for part in (raw or "").split(","):
        item = part.strip()
        if not item:
            continue
        if "://" in item:
            parsed = urlparse(item)
            key = _host_key(parsed.netloc)
            if key:
                hosts.add(key)
            continue
        hosts.add(_host_key(item))
    return {h for h in hosts if h}


def default_trusted_hosts(provider: str) -> set[str]:
    """Built-in trusted hosts for a known provider (R192)."""
    default = DEFAULT_BASE_URLS.get(provider, "")
    hosts: set[str] = set()
    if default:
        hosts |= _parse_allowlist_entries(default)
    if provider == PROVIDER_OLLAMA:
        hosts.update({"127.0.0.1", "localhost", "[::1]", "::1"})
    return hosts


def assert_trusted_base_url(
    provider: str,
    base_url: str,
    *,
    extra_allowlist: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Validate ``base_url`` against the trust allowlist; return stripped URL.

    Fail closed: unknown scheme/host raises ``AiBackendConfigError``.
    """
    url = (base_url or "").strip()
    if not url:
        raise AiBackendConfigError("AI base_url is empty")
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    host = _host_key(parsed.netloc)
    if scheme not in ("https", "http") or not host:
        raise AiBackendConfigError(f"AI base_url must be an absolute http(s) URL with a host: {url!r}")
    if scheme == "http" and host not in {"127.0.0.1", "localhost", "[::1]", "::1"}:
        raise AiBackendConfigError(f"AI base_url rejects cleartext http for non-loopback host: {url!r}")

    trusted = default_trusted_hosts(provider)
    env_map = environ if environ is not None else os.environ
    trusted |= _parse_allowlist_entries(env_map.get(_ALLOWLIST_ENV))
    if extra_allowlist:
        for entry in extra_allowlist:
            trusted |= _parse_allowlist_entries(entry)

    if host not in trusted:
        raise AiBackendConfigError(f"AI base_url host {host!r} is not on the trust allowlist for provider {provider!r}")
    return url.rstrip("/")


def _read_budgeted(
    response: Any,
    *,
    max_bytes: int = MAX_RESPONSE_BYTES,
    chunk_size: int = _READ_CHUNK_BYTES,
    should_cancel: Optional[CancelCheck] = None,
) -> bytes:
    """Read response body in chunks; enforce byte budget and optional cancel (R192)."""
    if max_bytes <= 0:
        raise AiHttpError("AI response byte budget must be positive")
    chunks: list[bytes] = []
    total = 0
    while True:
        if should_cancel is not None and should_cancel():
            raise AiHttpCancelled("AI provider request cancelled")
        try:
            piece = response.read(chunk_size)
        except TypeError:
            # Some fakes only implement read() with no size — still budget the result.
            piece = response.read()
            if not isinstance(piece, (bytes, bytearray)):
                raise AiHttpError("AI provider returned non-bytes body") from None
            if len(piece) > max_bytes:
                raise AiHttpError(f"AI provider response exceeds {max_bytes} byte budget") from None
            return bytes(piece)
        if not piece:
            break
        if not isinstance(piece, (bytes, bytearray)):
            raise AiHttpError("AI provider returned non-bytes body")
        total += len(piece)
        if total > max_bytes:
            raise AiHttpError(f"AI provider response exceeds {max_bytes} byte budget")
        chunks.append(bytes(piece))
    return b"".join(chunks)


def _http_json(
    url: str,
    payload: Mapping[str, object],
    headers: Mapping[str, str],
    *,
    timeout: float,
    opener: Optional[UrlOpener] = None,
    max_bytes: int = MAX_RESPONSE_BYTES,
    should_cancel: Optional[CancelCheck] = None,
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
            if should_cancel is not None and should_cancel():
                raise AiHttpCancelled("AI provider request cancelled")
            raw = _read_budgeted(
                response,
                max_bytes=max_bytes,
                should_cancel=should_cancel,
            )
            status = getattr(response, "status", None) or response.getcode()
    except AiHttpCancelled:
        raise
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = _read_budgeted(exc, max_bytes=min(max_bytes, 4096)).decode("utf-8", errors="replace")[:500]
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
        max_response_bytes: int = MAX_RESPONSE_BYTES,
        should_cancel: Optional[CancelCheck] = None,
        extra_allowlist: Sequence[str] | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self._config = config.normalized()
        self._api_key = (api_key or "").strip() or None
        self._timeout = float(timeout)
        self._opener = opener
        self._max_response_bytes = int(max_response_bytes)
        self._should_cancel = should_cancel
        provider = self._config.provider
        if provider not in (PROVIDER_OPENAI, PROVIDER_ANTHROPIC, PROVIDER_OLLAMA):
            raise AiBackendConfigError(f"HttpChatBackend does not support provider {provider!r}; use offline")
        if provider in (PROVIDER_OPENAI, PROVIDER_ANTHROPIC) and not self._api_key:
            raise AiBackendConfigError(
                f"API key required for provider {provider!r}. Set it in Options → AI → AI settings…"
            )
        # R192: refuse untrusted base_url before any network I/O.
        self._trusted_base = assert_trusted_base_url(
            provider,
            self._config.base_url,
            extra_allowlist=extra_allowlist,
            environ=environ,
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
        url = _join_url(self._trusted_base, "chat/completions")
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
            max_bytes=self._max_response_bytes,
            should_cancel=self._should_cancel,
        )
        return _openai_text(parsed)

    def _call_anthropic(self, prompt: str, *, system: str = "") -> str:
        url = _join_url(self._trusted_base, "v1/messages")
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
            max_bytes=self._max_response_bytes,
            should_cancel=self._should_cancel,
        )
        return _anthropic_text(parsed)


__all__ = [
    "AiBackendConfigError",
    "AiHttpCancelled",
    "AiHttpError",
    "HttpChatBackend",
    "MAX_RESPONSE_BYTES",
    "assert_trusted_base_url",
    "default_trusted_hosts",
]
