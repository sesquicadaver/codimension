# -*- coding: utf-8 -*-
"""R268: explicit AI budget kwargs fail-closed like environment parsers."""

from __future__ import annotations

import math

import pytest
from core.ai_budget import (
    AiBudgetConfigError,
    AiBudgetLimits,
    load_ai_budget_limits,
    load_ai_job_contract,
)


def test_r268_explicit_max_cost_usd_nan_rejected() -> None:
    with pytest.raises(AiBudgetConfigError, match="finite"):
        load_ai_budget_limits(max_cost_usd=math.nan)


def test_r268_explicit_max_cost_usd_negative_rejected() -> None:
    with pytest.raises(AiBudgetConfigError, match="non-negative"):
        load_ai_budget_limits(max_cost_usd=-0.01)


def test_r268_explicit_max_tokens_negative_rejected() -> None:
    with pytest.raises(AiBudgetConfigError, match="non-negative"):
        load_ai_budget_limits(max_tokens=-1)


def test_r268_explicit_usd_rate_inf_rejected() -> None:
    with pytest.raises(AiBudgetConfigError, match="finite"):
        load_ai_budget_limits(usd_per_1k_tokens=math.inf)


def test_r268_explicit_deadline_sec_nan_rejected() -> None:
    limits = AiBudgetLimits(max_tokens=1000, max_cost_usd=1.0)
    with pytest.raises(AiBudgetConfigError, match="finite"):
        load_ai_job_contract(limits=limits, deadline_sec=math.nan)


def test_r268_explicit_deadline_sec_negative_rejected() -> None:
    limits = AiBudgetLimits(max_tokens=1000, max_cost_usd=1.0)
    with pytest.raises(AiBudgetConfigError, match="non-negative"):
        load_ai_job_contract(limits=limits, deadline_sec=-5.0)


def test_r268_explicit_deadline_sec_positive_still_works() -> None:
    limits = AiBudgetLimits(max_tokens=1000, max_cost_usd=1.0)
    contract = load_ai_job_contract(limits=limits, deadline_sec=12.0, now=100.0)
    assert contract.deadline_monotonic == pytest.approx(112.0)


def test_r268_explicit_bool_max_tokens_rejected() -> None:
    with pytest.raises(AiBudgetConfigError, match="non-negative integer"):
        load_ai_budget_limits(max_tokens=True)  # type: ignore[arg-type]
