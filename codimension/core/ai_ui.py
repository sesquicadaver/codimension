# -*- coding: utf-8 -*-
#
# codimension - AI UI actions behind feature flag (R152)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""AI explain / suggest actions gated by feature flags (R152 / R174).

Headless orchestration: no Qt. Default backend is resolved from
:mod:`core.ai_config` (offline unless the user selects a remote provider).
UI layers must call :func:`is_ai_ui_enabled` before exposing menu entries.

Enable via persistent flag ``ai_ui`` (R174) or env ``CDM_AI_UI`` (override).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Mapping, MutableMapping, Optional, Protocol

from core.ai_config import (
    PROVIDER_ANTHROPIC,
    PROVIDER_OFFLINE,
    PROVIDER_OLLAMA,
    PROVIDER_OPENAI,
    describe_ai_provider_settings,
    get_ai_api_key,
    load_ai_config,
)
from core.ai_context import AiContextPack, build_ai_context_from_source
from core.ai_http import AiBackendConfigError, HttpChatBackend
from core.feature_flags import (
    FLAG_AI_UI,
    FLAG_ENV_OVERRIDES,
    FeatureFlagsStore,
    default_feature_flags_path,
    enable_flag_in_environ,
    get_feature_flags_store,
    is_feature_enabled,
    set_feature_enabled,
)
from core.symbol_index import SymbolKind

#: Environment variable that enables AI UI actions (default: off).
AI_UI_ENV = FLAG_ENV_OVERRIDES[FLAG_AI_UI]

#: Human-readable name of the default offline backend (no network / no API key).
AI_DEFAULT_BACKEND_LABEL = "offline-summary (local CFG/symbol pack; no LLM)"


def ai_ui_env_override_active(environ: Optional[Mapping[str, str]] = None) -> bool:
    """True when ``CDM_AI_UI`` is set (non-empty) and overrides the persistent flag."""
    env: Mapping[str, str] = os.environ if environ is None else environ
    return AI_UI_ENV in env and str(env.get(AI_UI_ENV, "")).strip() != ""


def set_ai_ui_enabled(
    enabled: bool,
    *,
    store: Optional[FeatureFlagsStore] = None,
    persist: bool = True,
) -> None:
    """Persist the ``ai_ui`` feature flag (Options / settings dialog)."""
    set_feature_enabled(FLAG_AI_UI, enabled, store=store, persist=persist)


def resolve_default_backend(
    *,
    home: Optional[str] = None,
    settings_path: Optional[str] = None,
    token_path: Optional[str] = None,
) -> AiBackend:
    """Build the configured backend (offline by default).

    Raises:
        AiBackendConfigError: remote provider selected but key/settings incomplete.
    """
    cfg = load_ai_config(path=settings_path, home=home)
    if cfg.provider == PROVIDER_OFFLINE:
        return OfflineSummaryBackend()
    api_key = get_ai_api_key(cfg.provider, home=home, token_path=token_path)
    if cfg.provider in (PROVIDER_OPENAI, PROVIDER_ANTHROPIC) and not api_key:
        raise AiBackendConfigError(
            f"API key required for provider {cfg.provider!r}. Set it in Options → AI → AI settings…"
        )
    if cfg.provider == PROVIDER_OLLAMA and not (cfg.base_url or "").strip():
        raise AiBackendConfigError("Ollama base URL is empty. Set it in AI settings…")
    backend: AiBackend = HttpChatBackend(cfg, api_key=api_key)
    return backend


def describe_ai_ui_settings(
    environ: Optional[Mapping[str, str]] = None,
    *,
    store: Optional[FeatureFlagsStore] = None,
    home: Optional[str] = None,
    settings_path: Optional[str] = None,
    token_path: Optional[str] = None,
) -> dict[str, object]:
    """Snapshot for the AI settings UI (flag, env override, provider, key status)."""
    active_store = store if store is not None else get_feature_flags_store()
    env_active = ai_ui_env_override_active(environ)
    provider_snap = describe_ai_provider_settings(
        home=home,
        settings_path=settings_path,
        token_path=token_path,
    )
    provider = str(provider_snap["provider"])
    if provider == PROVIDER_OFFLINE:
        backend_label = AI_DEFAULT_BACKEND_LABEL
    else:
        model = str(provider_snap.get("model") or "")
        key_note = "key OK" if provider_snap.get("api_key_configured") else "key missing"
        if provider == PROVIDER_OLLAMA:
            key_note = "local HTTP"
        backend_label = f"{provider} / {model} ({key_note})"
    return {
        "enabled": is_ai_ui_enabled(environ, store=store),
        "store_enabled": active_store.is_enabled(FLAG_AI_UI),
        "env_override_active": env_active,
        "env_key": AI_UI_ENV,
        "flags_path": active_store.path or default_feature_flags_path(),
        "backend_label": backend_label,
        "provider": provider,
        "provider_label": provider_snap.get("provider_label"),
        "model": provider_snap.get("model"),
        "base_url": provider_snap.get("base_url"),
        "requires_api_key": provider_snap.get("requires_api_key"),
        "api_key_configured": provider_snap.get("api_key_configured"),
        "settings_path": provider_snap.get("settings_path"),
    }


class AiUiDisabledError(RuntimeError):
    """Raised when an AI UI action is invoked while the feature flag is off."""


class AiAction(str, Enum):
    """Supported AI UI actions."""

    EXPLAIN = "explain"
    SUGGEST = "suggest"


@dataclass(frozen=True)
class AiActionResult:
    """Outcome of an explain / suggest run."""

    action: AiAction
    text: str
    symbol_name: str
    backend_name: str


class AiBackend(Protocol):
    """Pluggable backend for AI UI actions (may be mocked in tests)."""

    @property
    def name(self) -> str:
        """Short backend id for diagnostics."""

    def explain(self, pack: AiContextPack) -> str:
        """Return an explanation for ``pack``."""

    def suggest(self, pack: AiContextPack) -> str:
        """Return improvement suggestions for ``pack``."""


class OfflineSummaryBackend:
    """Default no-network backend: structured summary from the context pack."""

    @property
    def name(self) -> str:
        return "offline-summary"

    def explain(self, pack: AiContextPack) -> str:
        """Explain symbol using CFG slice and excerpt metadata."""
        lines = [
            f"Symbol: {pack.symbol.qualname or pack.symbol.name} ({pack.symbol.kind.value})",
            f"File: {pack.symbol.file}:{pack.excerpt_begin_line}-{pack.excerpt_end_line}",
            f"Definitions: {len(pack.definitions)}; references: {len(pack.references)}; related: {len(pack.related)}",
        ]
        if pack.cfg_slice is not None:
            kinds = sorted({n.kind.value for n in pack.cfg_slice.nodes})
            lines.append(
                f"CFG slice: root={pack.cfg_slice.root_id}; "
                f"nodes={len(pack.cfg_slice.nodes)}; edges={len(pack.cfg_slice.edges)}; "
                f"kinds={', '.join(kinds)}"
            )
        else:
            lines.append("CFG slice: none")
        if pack.notes:
            lines.append("Notes: " + "; ".join(pack.notes))
        excerpt_preview = pack.source_excerpt.strip().splitlines()[:8]
        if excerpt_preview:
            lines.append("Excerpt:")
            lines.extend(f"  {row}" for row in excerpt_preview)
        return "\n".join(lines)

    def suggest(self, pack: AiContextPack) -> str:
        """Heuristic suggestions derived from pack structure (no LLM)."""
        tips: list[str] = []
        if pack.cfg_slice is None:
            tips.append("No CFG scope matched — clarify the symbol under the cursor or save the buffer.")
        else:
            kind_counts: dict[str, int] = {}
            for node in pack.cfg_slice.nodes:
                kind_counts[node.kind.value] = kind_counts.get(node.kind.value, 0) + 1
            branches = kind_counts.get("if", 0) + kind_counts.get("match", 0)
            loops = kind_counts.get("for", 0) + kind_counts.get("while", 0)
            if branches >= 3:
                tips.append(f"High branch count ({branches}): consider extracting helpers.")
            if loops >= 2:
                tips.append(f"Multiple loops ({loops}): check nested iteration cost.")
            if not tips:
                tips.append(
                    f"CFG looks modest ({len(pack.cfg_slice.nodes)} nodes); "
                    "focus review on call sites and shared state."
                )
        if len(pack.references) > 10:
            tips.append(f"Many references ({len(pack.references)}): prefer rename/refactor tooling.")
        if pack.notes:
            tips.append("Context notes: " + "; ".join(pack.notes))
        header = f"Suggestions for {pack.symbol.qualname or pack.symbol.name}:"
        return header + "\n- " + "\n- ".join(tips)


class MockAiBackend:
    """Deterministic backend for smoke tests (no network)."""

    def __init__(self, *, prefix: str = "mock") -> None:
        self._prefix = prefix

    @property
    def name(self) -> str:
        return "mock"

    def explain(self, pack: AiContextPack) -> str:
        return f"{self._prefix}:explain:{pack.symbol.name}"

    def suggest(self, pack: AiContextPack) -> str:
        return f"{self._prefix}:suggest:{pack.symbol.name}"


def is_ai_ui_enabled(
    environ: Optional[Mapping[str, str]] = None,
    *,
    store: Optional[FeatureFlagsStore] = None,
) -> bool:
    """Return True when AI UI is enabled (env override or persistent ``ai_ui``)."""
    return bool(is_feature_enabled(FLAG_AI_UI, store=store, environ=environ))


def list_ai_menu_entries(
    environ: Optional[Mapping[str, str]] = None,
    *,
    store: Optional[FeatureFlagsStore] = None,
) -> tuple[tuple[AiAction, str], ...]:
    """Return ``(action, label)`` pairs for the editor menu, or empty when off."""
    if not is_ai_ui_enabled(environ, store=store):
        return ()
    return (
        (AiAction.EXPLAIN, "Explain with AI…"),
        (AiAction.SUGGEST, "Suggest with AI…"),
    )


def run_ai_action(
    action: AiAction,
    pack: AiContextPack,
    *,
    backend: Optional[AiBackend] = None,
    environ: Optional[Mapping[str, str]] = None,
    store: Optional[FeatureFlagsStore] = None,
    home: Optional[str] = None,
    settings_path: Optional[str] = None,
    token_path: Optional[str] = None,
) -> AiActionResult:
    """Run ``action`` on an existing pack; requires the feature flag."""
    if not is_ai_ui_enabled(environ, store=store):
        raise AiUiDisabledError(f"AI UI disabled (set {AI_UI_ENV}=1 or enable feature flag {FLAG_AI_UI!r})")
    active: AiBackend
    if backend is not None:
        active = backend
    else:
        active = resolve_default_backend(
            home=home,
            settings_path=settings_path,
            token_path=token_path,
        )
    if action is AiAction.EXPLAIN:
        text = active.explain(pack)
    elif action is AiAction.SUGGEST:
        text = active.suggest(pack)
    else:
        raise ValueError(f"unsupported AI action: {action!r}")
    return AiActionResult(
        action=action,
        text=text,
        symbol_name=pack.symbol.name,
        backend_name=active.name,
    )


def run_ai_action_for_source(
    action: AiAction,
    source: str,
    name: str,
    *,
    file: str = "<memory>",
    kind: Optional[SymbolKind] = None,
    backend: Optional[AiBackend] = None,
    environ: Optional[Mapping[str, str]] = None,
    store: Optional[FeatureFlagsStore] = None,
    home: Optional[str] = None,
    settings_path: Optional[str] = None,
    token_path: Optional[str] = None,
) -> AiActionResult:
    """Build context from ``source`` then run ``action`` (flag-gated)."""
    if not is_ai_ui_enabled(environ, store=store):
        raise AiUiDisabledError(f"AI UI disabled (set {AI_UI_ENV}=1 or enable feature flag {FLAG_AI_UI!r})")
    pack = build_ai_context_from_source(source, name, file=file, kind=kind)
    return run_ai_action(
        action,
        pack,
        backend=backend,
        environ=environ,
        store=store,
        home=home,
        settings_path=settings_path,
        token_path=token_path,
    )


def enable_ai_ui_for_tests(environ: MutableMapping[str, str]) -> None:
    """Set the env override in a mutable environ mapping (tests / smoke helpers)."""
    enable_flag_in_environ(FLAG_AI_UI, environ)


__all__ = [
    "AI_DEFAULT_BACKEND_LABEL",
    "AI_UI_ENV",
    "AiAction",
    "AiActionResult",
    "AiBackend",
    "AiBackendConfigError",
    "AiUiDisabledError",
    "MockAiBackend",
    "OfflineSummaryBackend",
    "ai_ui_env_override_active",
    "describe_ai_ui_settings",
    "enable_ai_ui_for_tests",
    "is_ai_ui_enabled",
    "list_ai_menu_entries",
    "resolve_default_backend",
    "run_ai_action",
    "run_ai_action_for_source",
    "set_ai_ui_enabled",
]
