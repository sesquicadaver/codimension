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

Headless orchestration: no Qt, no network. The default backend formats an
:class:`~core.ai_context.AiContextPack` locally (offline summary). UI layers
must call :func:`is_ai_ui_enabled` before exposing menu entries.

Enable via persistent flag ``ai_ui`` (R174) or env ``CDM_AI_UI`` (override).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, MutableMapping, Optional, Protocol

from core.ai_context import AiContextPack, build_ai_context_from_source
from core.feature_flags import (
    FLAG_AI_UI,
    FLAG_ENV_OVERRIDES,
    FeatureFlagsStore,
    enable_flag_in_environ,
    is_feature_enabled,
)
from core.symbol_index import SymbolKind

#: Environment variable that enables AI UI actions (default: off).
AI_UI_ENV = FLAG_ENV_OVERRIDES[FLAG_AI_UI]


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
) -> AiActionResult:
    """Run ``action`` on an existing pack; requires the feature flag."""
    if not is_ai_ui_enabled(environ, store=store):
        raise AiUiDisabledError(f"AI UI disabled (set {AI_UI_ENV}=1 or enable feature flag {FLAG_AI_UI!r})")
    active: AiBackend = backend if backend is not None else OfflineSummaryBackend()
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
) -> AiActionResult:
    """Build context from ``source`` then run ``action`` (flag-gated)."""
    if not is_ai_ui_enabled(environ, store=store):
        raise AiUiDisabledError(f"AI UI disabled (set {AI_UI_ENV}=1 or enable feature flag {FLAG_AI_UI!r})")
    pack = build_ai_context_from_source(source, name, file=file, kind=kind)
    return run_ai_action(action, pack, backend=backend, environ=environ, store=store)


def enable_ai_ui_for_tests(environ: MutableMapping[str, str]) -> None:
    """Set the env override in a mutable environ mapping (tests / smoke helpers)."""
    enable_flag_in_environ(FLAG_AI_UI, environ)


__all__ = [
    "AI_UI_ENV",
    "AiAction",
    "AiActionResult",
    "AiBackend",
    "AiUiDisabledError",
    "MockAiBackend",
    "OfflineSummaryBackend",
    "enable_ai_ui_for_tests",
    "is_ai_ui_enabled",
    "list_ai_menu_entries",
    "run_ai_action",
    "run_ai_action_for_source",
]
