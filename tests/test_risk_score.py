# -*- coding: utf-8 -*-
"""R138: composite risk score (lint + metrics + optional git)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


def test_clean_inputs_low_score() -> None:
    from core.risk_score import RiskInputs, compute_risk_score, risk_band

    report = compute_risk_score(RiskInputs(lint_issues=0, max_cc=1.0, maintainability_index=90.0, git_churn=0))
    assert report.score < 25
    assert risk_band(report.score) == "low"
    assert report.git_factor == 0.0
    assert abs(sum(report.weights.values()) - 1.0) < 1e-9


def test_heavy_lint_and_cc_raises_score() -> None:
    from core.risk_score import RiskInputs, compute_risk_score, risk_band

    clean = compute_risk_score(RiskInputs(lint_issues=0, max_cc=1.0, maintainability_index=90.0))
    dirty = compute_risk_score(RiskInputs(lint_issues=40, max_cc=40.0, maintainability_index=0.0, git_churn=400))
    assert dirty.score > clean.score
    assert dirty.score >= 75
    assert risk_band(dirty.score) == "high"
    assert dirty.lint_factor == 1.0
    assert dirty.metrics_factor == 1.0
    assert dirty.git_factor == 1.0


def test_omit_git_renormalizes_weights() -> None:
    from core.risk_score import DEFAULT_WEIGHTS, RiskInputs, compute_risk_score

    report = compute_risk_score(RiskInputs(lint_issues=10, max_cc=10.0, maintainability_index=50.0))
    assert report.git_factor is None
    assert "git" not in report.weights
    expected_lint = DEFAULT_WEIGHTS["lint"] / (DEFAULT_WEIGHTS["lint"] + DEFAULT_WEIGHTS["metrics"])
    assert abs(report.weights["lint"] - expected_lint) < 1e-9
    assert abs(sum(report.weights.values()) - 1.0) < 1e-9


def test_metrics_only_cc_or_only_mi() -> None:
    from core.risk_score import metrics_factor, metrics_factor_detailed

    cc_only = metrics_factor(10.0, None, cc_cap=20.0)
    assert abs(cc_only - 0.5) < 1e-9
    mi_only = metrics_factor(None, 0.0)
    assert abs(mi_only - 1.0) < 1e-9
    neither = metrics_factor_detailed(None, None)
    assert neither.status == "unknown"
    assert neither.factor == 0.5
    assert neither.coverage == 0.0


def test_r194_missing_metrics_do_not_understate_risk() -> None:
    """A222: missing CC/MI must not score like a clean metrics profile."""
    from core.risk_score import RiskInputs, compute_risk_score, risk_band_with_confidence

    with_metrics = compute_risk_score(RiskInputs(lint_issues=0, max_cc=1.0, maintainability_index=95.0))
    missing = compute_risk_score(RiskInputs(lint_issues=0, max_cc=None, maintainability_index=None))
    assert missing.metrics_status == "unknown"
    assert missing.metrics_factor == 0.5
    assert missing.score > with_metrics.score
    assert missing.confidence < with_metrics.confidence
    assert risk_band_with_confidence(missing) == "unknown"
    assert risk_band_with_confidence(with_metrics) != "unknown"


def test_deterministic_and_documented_formula_id() -> None:
    from core.risk_score import FORMULA_ID, RiskInputs, compute_risk_score

    inputs = RiskInputs(lint_issues=5, max_cc=8.0, maintainability_index=70.0, git_churn=50)
    a = compute_risk_score(inputs)
    b = compute_risk_score(inputs)
    assert a == b
    assert a.formula_id == FORMULA_ID == "cdm-risk-v2"
    assert a.confidence == 1.0
    assert a.metrics_status == "full"


def test_rejects_negative_lint() -> None:
    from core.risk_score import RiskInputs, compute_risk_score

    with pytest.raises(ValueError, match="lint_issues"):
        compute_risk_score(RiskInputs(lint_issues=-1))


def test_core_risk_score_import_without_qt() -> None:
    root = Path(__file__).resolve().parents[1]
    code = (
        "import sys\n"
        f"sys.path.insert(0, {str(root / 'codimension')!r})\n"
        f"sys.path.insert(0, {str(root)!r})\n"
        "assert 'PyQt5' not in sys.modules\n"
        "from core.risk_score import compute_risk_score, RiskInputs\n"
        "assert 'PyQt5' not in sys.modules\n"
        "print('ok')\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)
    assert "ok" in proc.stdout
