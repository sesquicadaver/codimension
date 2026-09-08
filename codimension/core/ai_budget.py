# -*- coding: utf-8 -*-
#
# codimension - AI session token/cost budgets (R231 / R241)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Global (per-job) AI token/cost budgets beyond per-file truncation (R231 / R241 / R249).

Token counts are **estimates** (``chars / 4``) suitable for fail-closed
caps — not billing-grade metering. Cost uses a configurable USD-per-1k-tokens
rate so offline/fake backends still exercise the same gates.

R241: invalid environment values fail closed; ``record`` rejects over-budget
completions; :class:`AiJobContract` adds file/request/source/output/deadline
ceilings for project analysis.

R249: ``remaining_output_tokens`` also respects remaining cost (converted to
tokens); callers must preflight with that provider cap, not a fixed reserve.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Mapping, Optional

#: Env: hard cap on estimated tokens (prompt + completion) for one AI job.
ENV_AI_MAX_TOKENS = "CDM_AI_MAX_TOKENS"
#: Env: hard cap on estimated USD cost for one AI job.
ENV_AI_MAX_COST_USD = "CDM_AI_MAX_COST_USD"
#: Env: USD charged per 1000 estimated tokens.
ENV_AI_USD_PER_1K_TOKENS = "CDM_AI_USD_PER_1K_TOKENS"
#: Env: max project files analyzed in one job (R241).
ENV_AI_MAX_FILES = "CDM_AI_MAX_FILES"
#: Env: max provider requests (chunk + synthesis) in one job (R241).
ENV_AI_MAX_REQUESTS = "CDM_AI_MAX_REQUESTS"
#: Env: max bytes read from one source file before truncation (R241).
ENV_AI_MAX_SOURCE_BYTES = "CDM_AI_MAX_SOURCE_BYTES"
#: Env: max output tokens passed to the provider per request (R241).
ENV_AI_MAX_OUTPUT_TOKENS = "CDM_AI_MAX_OUTPUT_TOKENS"
#: Env: wall-clock deadline in seconds from job start (R241).
ENV_AI_DEADLINE_SEC = "CDM_AI_DEADLINE_SEC"

DEFAULT_MAX_TOKENS = 100_000
DEFAULT_MAX_COST_USD = 1.0
DEFAULT_USD_PER_1K = 0.002
DEFAULT_COMPLETION_RESERVE = 2_000
DEFAULT_MAX_FILES = 200
DEFAULT_MAX_REQUESTS = 250
DEFAULT_MAX_SOURCE_BYTES = 512_000
DEFAULT_MAX_OUTPUT_TOKENS = 4_096
DEFAULT_DEADLINE_SEC = 0  # 0 = no deadline


class AiBudgetExceeded(RuntimeError):
    """Raised when an AI job would exceed the configured global budget."""

    def __init__(self, message: str, *, tokens_used: int = 0, cost_usd: float = 0.0) -> None:
        self.tokens_used = tokens_used
        self.cost_usd = cost_usd
        super().__init__(message)


class AiBudgetConfigError(ValueError):
    """Raised when budget environment values are present but invalid (R241)."""


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


@dataclass(frozen=True, slots=True)
class AiJobContract:
    """Immutable hard caps for one AI job (R241).

    ``deadline_monotonic`` is an absolute :func:`time.monotonic` timestamp, or
    ``None`` when no wall-clock deadline applies.
    """

    limits: AiBudgetLimits
    max_files: int = DEFAULT_MAX_FILES
    max_requests: int = DEFAULT_MAX_REQUESTS
    max_source_bytes: int = DEFAULT_MAX_SOURCE_BYTES
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    deadline_monotonic: float | None = None

    def __post_init__(self) -> None:
        if self.max_files < 0:
            raise ValueError("max_files must be >= 0")
        if self.max_requests < 0:
            raise ValueError("max_requests must be >= 0")
        if self.max_source_bytes < 0:
            raise ValueError("max_source_bytes must be >= 0")
        if self.max_output_tokens < 0:
            raise ValueError("max_output_tokens must be >= 0")

    def deadline_exceeded(self, *, now: float | None = None) -> bool:
        """True when a deadline is set and ``now`` is past it."""
        if self.deadline_monotonic is None:
            return False
        clock = time.monotonic() if now is None else now
        return clock >= self.deadline_monotonic


def estimate_tokens(text: str) -> int:
    """Rough token estimate from character length (``ceil(chars / 4)``)."""
    chars = len(text or "")
    if chars <= 0:
        return 0
    return (chars + 3) // 4


def _env_int_strict(environ: Mapping[str, str], key: str, default: int) -> int:
    """Parse a non-negative int; empty → default; invalid → :class:`AiBudgetConfigError`."""
    raw = (environ.get(key) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise AiBudgetConfigError(f"invalid {key}={raw!r}; expected non-negative integer") from exc
    if value < 0:
        raise AiBudgetConfigError(f"invalid {key}={raw!r}; expected non-negative integer")
    return value


def _env_float_strict(environ: Mapping[str, str], key: str, default: float) -> float:
    """Parse a non-negative float; empty → default; invalid → :class:`AiBudgetConfigError`."""
    raw = (environ.get(key) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise AiBudgetConfigError(f"invalid {key}={raw!r}; expected non-negative number") from exc
    if value < 0:
        raise AiBudgetConfigError(f"invalid {key}={raw!r}; expected non-negative number")
    return value


def load_ai_budget_limits(
    *,
    environ: Optional[Mapping[str, str]] = None,
    max_tokens: Optional[int] = None,
    max_cost_usd: Optional[float] = None,
    usd_per_1k_tokens: Optional[float] = None,
) -> AiBudgetLimits:
    """Build limits from explicit kwargs, else environment, else defaults.

    R241: malformed environment values raise :class:`AiBudgetConfigError`
    (fail-closed) instead of silently falling back to defaults.
    """
    env = environ if environ is not None else os.environ
    tokens = _env_int_strict(env, ENV_AI_MAX_TOKENS, DEFAULT_MAX_TOKENS) if max_tokens is None else max_tokens
    cost = _env_float_strict(env, ENV_AI_MAX_COST_USD, DEFAULT_MAX_COST_USD) if max_cost_usd is None else max_cost_usd
    rate = (
        _env_float_strict(env, ENV_AI_USD_PER_1K_TOKENS, DEFAULT_USD_PER_1K)
        if usd_per_1k_tokens is None
        else usd_per_1k_tokens
    )
    return AiBudgetLimits(max_tokens=tokens, max_cost_usd=cost, usd_per_1k_tokens=rate)


def load_ai_job_contract(
    *,
    environ: Optional[Mapping[str, str]] = None,
    limits: Optional[AiBudgetLimits] = None,
    deadline_sec: Optional[float] = None,
    now: float | None = None,
) -> AiJobContract:
    """Load an :class:`AiJobContract` from environment / defaults (R241)."""
    env = environ if environ is not None else os.environ
    budget = limits if limits is not None else load_ai_budget_limits(environ=env)
    max_files = _env_int_strict(env, ENV_AI_MAX_FILES, DEFAULT_MAX_FILES)
    max_requests = _env_int_strict(env, ENV_AI_MAX_REQUESTS, DEFAULT_MAX_REQUESTS)
    max_source_bytes = _env_int_strict(env, ENV_AI_MAX_SOURCE_BYTES, DEFAULT_MAX_SOURCE_BYTES)
    max_output_tokens = _env_int_strict(env, ENV_AI_MAX_OUTPUT_TOKENS, DEFAULT_MAX_OUTPUT_TOKENS)
    if deadline_sec is None:
        deadline_sec = _env_float_strict(env, ENV_AI_DEADLINE_SEC, float(DEFAULT_DEADLINE_SEC))
    deadline_monotonic: float | None = None
    if deadline_sec and deadline_sec > 0:
        clock = time.monotonic() if now is None else now
        deadline_monotonic = clock + float(deadline_sec)
    return AiJobContract(
        limits=budget,
        max_files=max_files,
        max_requests=max_requests,
        max_source_bytes=max_source_bytes,
        max_output_tokens=max_output_tokens,
        deadline_monotonic=deadline_monotonic,
    )


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

    def remaining_output_tokens(self, prompt_tokens: int = 0, *, cap: int | None = None) -> int:
        """Output tokens still affordable after ``prompt_tokens``, optionally capped.

        R249: the result is the minimum of (1) remaining token budget after the
        prompt, (2) remaining cost converted to tokens after the prompt, and
        (3) optional ``cap`` (typically ``contract.max_output_tokens``).
        """
        prompt = max(0, int(prompt_tokens))
        left = self.remaining_tokens() - prompt
        if left <= 0:
            return 0

        rate = float(self.limits.usd_per_1k_tokens)
        if rate > 0:
            # How many total tokens (prompt+output) the remaining USD can buy.
            affordable_total = int(self.remaining_cost_usd() * 1000.0 / rate + 1e-12)
            left_cost = affordable_total - prompt
            if left_cost <= 0:
                return 0
            left = min(left, left_cost)

        if cap is not None:
            left = min(left, max(0, int(cap)))
        return left

    def can_afford(self, prompt_tokens: int, completion_tokens: int = DEFAULT_COMPLETION_RESERVE) -> bool:
        """True when adding the estimated spend stays within both ceilings."""
        need = max(0, int(prompt_tokens)) + max(0, int(completion_tokens))
        if self.tokens_used + need > self.limits.max_tokens:
            return False
        if self.cost_usd + self.cost_for_tokens(need) > self.limits.max_cost_usd + 1e-12:
            return False
        return True

    def record(self, prompt_tokens: int, completion_tokens: int = 0, *, hard: bool = True) -> None:
        """Accumulate spent tokens/cost; ``hard`` rejects over-budget completions (R241)."""
        spent_prompt = max(0, int(prompt_tokens))
        spent_completion = max(0, int(completion_tokens))
        spent = spent_prompt + spent_completion
        new_tokens = self.tokens_used + spent
        new_cost = self.cost_usd + self.cost_for_tokens(spent)
        if hard and (new_tokens > self.limits.max_tokens or new_cost > self.limits.max_cost_usd + 1e-12):
            raise AiBudgetExceeded(
                f"AI budget exceeded after response "
                f"(tokens {new_tokens}/{self.limits.max_tokens}, "
                f"cost ${new_cost:.6f}/${self.limits.max_cost_usd})",
                tokens_used=new_tokens,
                cost_usd=new_cost,
            )
        self.tokens_used = new_tokens
        self.cost_usd = new_cost

    def record_texts(self, prompt: str, completion: str = "", *, hard: bool = True) -> None:
        """Record spend from prompt/completion text lengths."""
        self.record(estimate_tokens(prompt), estimate_tokens(completion), hard=hard)


__all__ = [
    "AiBudgetConfigError",
    "AiBudgetExceeded",
    "AiBudgetLimits",
    "AiBudgetTracker",
    "AiJobContract",
    "DEFAULT_COMPLETION_RESERVE",
    "DEFAULT_DEADLINE_SEC",
    "DEFAULT_MAX_COST_USD",
    "DEFAULT_MAX_FILES",
    "DEFAULT_MAX_OUTPUT_TOKENS",
    "DEFAULT_MAX_REQUESTS",
    "DEFAULT_MAX_SOURCE_BYTES",
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_USD_PER_1K",
    "ENV_AI_DEADLINE_SEC",
    "ENV_AI_MAX_COST_USD",
    "ENV_AI_MAX_FILES",
    "ENV_AI_MAX_OUTPUT_TOKENS",
    "ENV_AI_MAX_REQUESTS",
    "ENV_AI_MAX_SOURCE_BYTES",
    "ENV_AI_MAX_TOKENS",
    "ENV_AI_USD_PER_1K_TOKENS",
    "estimate_tokens",
    "load_ai_budget_limits",
    "load_ai_job_contract",
]
