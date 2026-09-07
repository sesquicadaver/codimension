# -*- coding: utf-8 -*-
#
# codimension - AI session token/cost budgets (R231)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Global (per-job) AI token/cost budgets beyond per-file truncation (R231).

Token counts are **estimates** (``chars / 4``) suitable for fail-closed
caps — not billing-grade metering. Cost uses a configurable USD-per-1k-tokens
rate so offline/fake backends still exercise the same gates.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional

#: Env: hard cap on estimated tokens (prompt + completion) for one AI job.
ENV_AI_MAX_TOKENS = "CDM_AI_MAX_TOKENS"
#: Env: hard cap on estimated USD cost for one AI job.
ENV_AI_MAX_COST_USD = "CDM_AI_MAX_COST_USD"
#: Env: USD charged per 1000 estimated tokens.
ENV_AI_USD_PER_1K_TOKENS = "CDM_AI_USD_PER_1K_TOKENS"

DEFAULT_MAX_TOKENS = 100_000
DEFAULT_MAX_COST_USD = 1.0
DEFAULT_USD_PER_1K = 0.002
DEFAULT_COMPLETION_RESERVE = 2_000


class AiBudgetExceeded(RuntimeError):
    """Raised when an AI job would exceed the configured global budget."""

    def __init__(self, message: str, *, tokens_used: int = 0, cost_usd: float = 0.0) -> None:
        self.tokens_used = tokens_used
        self.cost_usd = cost_usd
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class AiBudgetLimits:
    """Immutable budget ceilings for one AI job."""

    max_tokens: int = DEFAULT_MAX_TOKENS
    max_cost_usd: float = DEFAULT_MAX_COST_USD
    usd_per_1k_tokens: float = DEFAULT_USD_PER_1K

    def __post_init__(self) -> None:
        if self.max_tokens < 0:
            raise ValueError("max_tokens must be >= 0")
        if self.max_cost_usd < 0:
            raise ValueError("max_cost_usd must be >= 0")
        if self.usd_per_1k_tokens < 0:
            raise ValueError("usd_per_1k_tokens must be >= 0")


def estimate_tokens(text: str) -> int:
    """Rough token estimate from character length (``ceil(chars / 4)``)."""
    chars = len(text or "")
    if chars <= 0:
        return 0
    return (chars + 3) // 4


def _env_int(environ: Mapping[str, str], key: str, default: int) -> int:
    raw = (environ.get(key) or "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def _env_float(environ: Mapping[str, str], key: str, default: float) -> float:
    raw = (environ.get(key) or "").strip()
    if not raw:
        return default
    try:
        return max(0.0, float(raw))
    except ValueError:
        return default


def load_ai_budget_limits(
    *,
    environ: Optional[Mapping[str, str]] = None,
    max_tokens: Optional[int] = None,
    max_cost_usd: Optional[float] = None,
    usd_per_1k_tokens: Optional[float] = None,
) -> AiBudgetLimits:
    """Build limits from explicit kwargs, else environment, else defaults."""
    env = environ if environ is not None else os.environ
    tokens = _env_int(env, ENV_AI_MAX_TOKENS, DEFAULT_MAX_TOKENS) if max_tokens is None else max_tokens
    cost = _env_float(env, ENV_AI_MAX_COST_USD, DEFAULT_MAX_COST_USD) if max_cost_usd is None else max_cost_usd
    rate = (
        _env_float(env, ENV_AI_USD_PER_1K_TOKENS, DEFAULT_USD_PER_1K)
        if usd_per_1k_tokens is None
        else usd_per_1k_tokens
    )
    return AiBudgetLimits(max_tokens=tokens, max_cost_usd=cost, usd_per_1k_tokens=rate)


@dataclass
class AiBudgetTracker:
    """Mutable accumulator for estimated tokens/cost within one AI job."""

    limits: AiBudgetLimits
    tokens_used: int = 0
    cost_usd: float = 0.0

    def cost_for_tokens(self, tokens: int) -> float:
        """USD estimate for ``tokens`` at the configured rate."""
        if tokens <= 0:
            return 0.0
        return (tokens / 1000.0) * self.limits.usd_per_1k_tokens

    def remaining_tokens(self) -> int:
        """Tokens left under the ceiling (0 when exhausted)."""
        return max(0, self.limits.max_tokens - self.tokens_used)

    def remaining_cost_usd(self) -> float:
        """USD left under the ceiling."""
        return max(0.0, self.limits.max_cost_usd - self.cost_usd)

    def can_afford(self, prompt_tokens: int, completion_tokens: int = DEFAULT_COMPLETION_RESERVE) -> bool:
        """True when adding the estimated spend stays within both ceilings."""
        need = max(0, int(prompt_tokens)) + max(0, int(completion_tokens))
        if self.tokens_used + need > self.limits.max_tokens:
            return False
        if self.cost_usd + self.cost_for_tokens(need) > self.limits.max_cost_usd + 1e-12:
            return False
        return True

    def record(self, prompt_tokens: int, completion_tokens: int = 0) -> None:
        """Accumulate spent tokens/cost (clamped at zero)."""
        spent = max(0, int(prompt_tokens)) + max(0, int(completion_tokens))
        self.tokens_used += spent
        self.cost_usd += self.cost_for_tokens(spent)

    def record_texts(self, prompt: str, completion: str = "") -> None:
        """Record spend from prompt/completion text lengths."""
        self.record(estimate_tokens(prompt), estimate_tokens(completion))


__all__ = [
    "AiBudgetExceeded",
    "AiBudgetLimits",
    "AiBudgetTracker",
    "DEFAULT_COMPLETION_RESERVE",
    "DEFAULT_MAX_COST_USD",
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_USD_PER_1K",
    "ENV_AI_MAX_COST_USD",
    "ENV_AI_MAX_TOKENS",
    "ENV_AI_USD_PER_1K_TOKENS",
    "estimate_tokens",
    "load_ai_budget_limits",
]
