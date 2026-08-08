# -*- coding: utf-8 -*-
#
# codimension - composite risk score (R138)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Composite risk score from lint + metrics + optional git (R138).

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
  ``MI_inv = 1 - clamp(mi / 100, 0, 1)``. Missing CC or MI drops that
  sub-weight and renormalizes within M (if both missing, ``M=0``).
* **G (git)** — ``min(1, git_churn / churn_cap)`` (default ``churn_cap=200``).

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


@dataclass(frozen=True, slots=True)
class RiskInputs:
    """Raw inputs for :func:`compute_risk_score`."""

    lint_issues: int = 0
    max_cc: Optional[float] = None
    maintainability_index: Optional[float] = None
    git_churn: Optional[int] = None


@dataclass(frozen=True, slots=True)
class RiskBreakdown:
    """Per-component factors and the final score."""

    score: float
    lint_factor: float
    metrics_factor: float
    git_factor: Optional[float]
    weights: Mapping[str, float]
    formula_id: str = "cdm-risk-v1"


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


def metrics_factor(
    max_cc: Optional[float],
    maintainability_index: Optional[float],
    *,
    cc_cap: float = DEFAULT_CAPS["cc"],
) -> float:
    """Blend cyclomatic complexity and inverted maintainability index."""
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
        return 0.0
    weight_sum = sum(w for w, _ in parts)
    return sum(w * v for w, v in parts) / weight_sum


def git_factor(git_churn: int, *, churn_cap: float = DEFAULT_CAPS["churn"]) -> float:
    """Normalize file churn (insertions+deletions) to ``[0, 1]``."""
    if git_churn < 0:
        raise ValueError("git_churn must be >= 0")
    if churn_cap <= 0:
        raise ValueError("churn_cap must be > 0")
    return clamp01(git_churn / churn_cap)


def compute_risk_score(
    inputs: RiskInputs,
    *,
    weights: Optional[Mapping[str, float]] = None,
    caps: Optional[Mapping[str, float]] = None,
) -> RiskBreakdown:
    """Compute the composite risk score for ``inputs``.

    See module docstring for the formula. Returns a :class:`RiskBreakdown`
    with factors and the effective weights used.
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
    m_factor = metrics_factor(
        inputs.max_cc,
        inputs.maintainability_index,
        cc_cap=float(c["cc"]),
    )

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
    else:
        total = w["lint"] + w["metrics"] + w["git"]
        effective = {
            "lint": w["lint"] / total,
            "metrics": w["metrics"] / total,
            "git": w["git"] / total,
        }
        g_factor = git_factor(inputs.git_churn, churn_cap=float(c["churn"]))
        score = 100.0 * (effective["lint"] * l_factor + effective["metrics"] * m_factor + effective["git"] * g_factor)

    return RiskBreakdown(
        score=round(score, 6),
        lint_factor=l_factor,
        metrics_factor=m_factor,
        git_factor=g_factor,
        weights=effective,
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


__all__ = [
    "DEFAULT_CAPS",
    "DEFAULT_WEIGHTS",
    "RiskBreakdown",
    "RiskInputs",
    "clamp01",
    "compute_risk_score",
    "git_factor",
    "lint_factor",
    "metrics_factor",
    "risk_band",
]
