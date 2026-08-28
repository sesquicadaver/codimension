# -*- coding: utf-8 -*-
#
# codimension - composite risk score (R138 / R194)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Composite risk score from lint + metrics + optional git (R138 / R194).

Deterministic, AI-free formula. All component factors are in ``[0, 1]``
(higher = worse). The final score is ``100 * weighted_sum`` in ``[0, 100]``.

Formula
-------
With git input present::

    score = 100 * (W_LINT * L + W_METRICS * M + W_GIT * G)

Without git (``git_churn`` is ``None``)::

    score = 100 * (W_LINT' * L + W_METRICS' * M)

where ``W_*'`` are the lint/metrics weights renormalized to sum to 1.

Defaults: ``W_LINT=0.35``, ``W_METRICS=0.45``, ``W_GIT=0.20``.

Component factors
-----------------
* **L (lint)** — ``min(1, lint_issues / lint_cap)`` (default ``lint_cap=20``).
* **M (metrics)** — ``0.6 * CC + 0.4 * MI_inv`` where
  ``CC = min(1, max_cc / cc_cap)`` (default ``cc_cap=20``) and
  ``MI_inv = 1 - clamp(mi / 100, 0, 1)``.
  **R194 / A222:** if both CC and MI are missing, ``M`` is the neutral
  unknown factor ``0.5`` (not ``0``) so missing data cannot understate risk.
  Partial metrics renormalize within M and lower ``confidence``.
* **G (git)** — ``min(1, git_churn / churn_cap)`` (default ``churn_cap=200``).

``confidence`` is in ``[0, 1]`` and reflects how complete the inputs are
(metrics coverage + whether git was supplied when weights include git).

No network, no ML, no randomness.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

DEFAULT_WEIGHTS: Mapping[str, float] = {
    "lint": 0.35,
    "metrics": 0.45,
    "git": 0.20,
}

DEFAULT_CAPS: Mapping[str, float] = {
    "lint": 20.0,
    "cc": 20.0,
    "churn": 200.0,
}

# Neutral factor when metrics are entirely unknown (R194).
UNKNOWN_METRICS_FACTOR = 0.5

FORMULA_ID = "cdm-risk-v2"


@dataclass(frozen=True, slots=True)
class RiskInputs:
    """Raw inputs for :func:`compute_risk_score`."""

    lint_issues: int = 0
    max_cc: Optional[float] = None
    maintainability_index: Optional[float] = None
    git_churn: Optional[int] = None


@dataclass(frozen=True, slots=True)
class MetricsFactorResult:
    """Metrics blend plus coverage metadata (R194)."""

    factor: float
    status: str  # "full" | "partial" | "unknown"
    coverage: float  # 0..1 share of CC/MI sub-weights present


@dataclass(frozen=True, slots=True)
class RiskBreakdown:
    """Per-component factors and the final score."""

    score: float
    lint_factor: float
    metrics_factor: float
    git_factor: Optional[float]
    weights: Mapping[str, float]
    confidence: float
    metrics_status: str
    formula_id: str = FORMULA_ID


def clamp01(value: float) -> float:
    """Clamp ``value`` into ``[0, 1]``."""
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return float(value)


def lint_factor(lint_issues: int, *, lint_cap: float = DEFAULT_CAPS["lint"]) -> float:
    """Normalize lint issue count to ``[0, 1]``."""
    if lint_issues < 0:
        raise ValueError("lint_issues must be >= 0")
    if lint_cap <= 0:
        raise ValueError("lint_cap must be > 0")
    return clamp01(lint_issues / lint_cap)


def metrics_factor_detailed(
    max_cc: Optional[float],
    maintainability_index: Optional[float],
    *,
    cc_cap: float = DEFAULT_CAPS["cc"],
    unknown_factor: float = UNKNOWN_METRICS_FACTOR,
) -> MetricsFactorResult:
    """Blend CC + inverted MI; never treat total absence as ``0`` risk (R194)."""
    if cc_cap <= 0:
        raise ValueError("cc_cap must be > 0")
    parts: list[tuple[float, float]] = []
    if max_cc is not None:
        if max_cc < 0:
            raise ValueError("max_cc must be >= 0")
        parts.append((0.6, clamp01(max_cc / cc_cap)))
    if maintainability_index is not None:
        mi = clamp01(maintainability_index / 100.0)
        parts.append((0.4, clamp01(1.0 - mi)))
    if not parts:
        return MetricsFactorResult(factor=float(unknown_factor), status="unknown", coverage=0.0)
    weight_sum = sum(w for w, _ in parts)
    coverage = weight_sum / 1.0  # CC+MI weights are 0.6+0.4
    factor = sum(w * v for w, v in parts) / weight_sum
    status = "full" if len(parts) == 2 else "partial"
    return MetricsFactorResult(factor=factor, status=status, coverage=coverage)


def metrics_factor(
    max_cc: Optional[float],
    maintainability_index: Optional[float],
    *,
    cc_cap: float = DEFAULT_CAPS["cc"],
) -> float:
    """Blend cyclomatic complexity and inverted maintainability index."""
    return metrics_factor_detailed(max_cc, maintainability_index, cc_cap=cc_cap).factor


def git_factor(git_churn: int, *, churn_cap: float = DEFAULT_CAPS["churn"]) -> float:
    """Normalize file churn (insertions+deletions) to ``[0, 1]``."""
    if git_churn < 0:
        raise ValueError("git_churn must be >= 0")
    if churn_cap <= 0:
        raise ValueError("churn_cap must be > 0")
    return clamp01(git_churn / churn_cap)


def _confidence(*, metrics_coverage: float, git_provided: bool, include_git_weight: bool) -> float:
    """Estimate input completeness in ``[0, 1]`` (R194)."""
    # Lint is always supplied as a count (including 0) → always "known".
    # Metrics: coverage of CC/MI sub-weights. Git: known only when provided.
    if include_git_weight:
        # Relative importance mirrors default weight mass (lint ignored as always present).
        metrics_share = 0.45 / (0.45 + 0.20)
        git_share = 0.20 / (0.45 + 0.20)
        git_cov = 1.0 if git_provided else 0.0
        return clamp01(metrics_share * metrics_coverage + git_share * git_cov)
    return clamp01(metrics_coverage)


def compute_risk_score(
    inputs: RiskInputs,
    *,
    weights: Optional[Mapping[str, float]] = None,
    caps: Optional[Mapping[str, float]] = None,
) -> RiskBreakdown:
    """Compute the composite risk score for ``inputs``.

    See module docstring for the formula. Returns a :class:`RiskBreakdown`
    with factors, confidence, and the effective weights used.
    """
    w = dict(DEFAULT_WEIGHTS if weights is None else weights)
    c = dict(DEFAULT_CAPS if caps is None else caps)
    for key in ("lint", "metrics", "git"):
        if key not in w:
            raise ValueError(f"weights missing {key!r}")
        if w[key] < 0:
            raise ValueError(f"weight {key!r} must be >= 0")
    if sum(w.values()) <= 0:
        raise ValueError("weights must sum to a positive value")

    l_factor = lint_factor(inputs.lint_issues, lint_cap=float(c["lint"]))
    metrics = metrics_factor_detailed(
        inputs.max_cc,
        inputs.maintainability_index,
        cc_cap=float(c["cc"]),
    )
    m_factor = metrics.factor

    if inputs.git_churn is None:
        total = w["lint"] + w["metrics"]
        if total <= 0:
            raise ValueError("lint+metrics weights must be > 0 when git is omitted")
        effective = {
            "lint": w["lint"] / total,
            "metrics": w["metrics"] / total,
        }
        g_factor: Optional[float] = None
        score = 100.0 * (effective["lint"] * l_factor + effective["metrics"] * m_factor)
        confidence = _confidence(
            metrics_coverage=metrics.coverage,
            git_provided=False,
            include_git_weight=False,
        )
    else:
        total = w["lint"] + w["metrics"] + w["git"]
        effective = {
            "lint": w["lint"] / total,
            "metrics": w["metrics"] / total,
            "git": w["git"] / total,
        }
        g_factor = git_factor(inputs.git_churn, churn_cap=float(c["churn"]))
        score = 100.0 * (effective["lint"] * l_factor + effective["metrics"] * m_factor + effective["git"] * g_factor)
        confidence = _confidence(
            metrics_coverage=metrics.coverage,
            git_provided=True,
            include_git_weight=True,
        )

    return RiskBreakdown(
        score=round(score, 6),
        lint_factor=l_factor,
        metrics_factor=m_factor,
        git_factor=g_factor,
        weights=effective,
        confidence=round(confidence, 6),
        metrics_status=metrics.status,
    )


def risk_band(score: float) -> str:
    """Map a 0–100 score to a coarse band label."""
    if score < 0 or score > 100:
        raise ValueError("score must be in [0, 100]")
    if score < 25:
        return "low"
    if score < 50:
        return "moderate"
    if score < 75:
        return "elevated"
    return "high"


def risk_band_with_confidence(breakdown: RiskBreakdown, *, min_confidence: float = 0.35) -> str:
    """Like :func:`risk_band`, but return ``unknown`` when confidence is too low (R194)."""
    if breakdown.confidence < min_confidence:
        return "unknown"
    return risk_band(breakdown.score)


__all__ = [
    "DEFAULT_CAPS",
    "DEFAULT_WEIGHTS",
    "FORMULA_ID",
    "UNKNOWN_METRICS_FACTOR",
    "MetricsFactorResult",
    "RiskBreakdown",
    "RiskInputs",
    "clamp01",
    "compute_risk_score",
    "git_factor",
    "lint_factor",
    "metrics_factor",
    "metrics_factor_detailed",
    "risk_band",
    "risk_band_with_confidence",
]
