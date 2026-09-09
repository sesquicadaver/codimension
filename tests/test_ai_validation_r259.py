# -*- coding: utf-8 -*-
"""R259: AI validation — evidence in line range; finite budget floats."""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from core.ai_budget import (
    ENV_AI_MAX_COST_USD,
    ENV_AI_USD_PER_1K_TOKENS,
    AiBudgetConfigError,
    AiBudgetLimits,
    AiJobContract,
    load_ai_budget_limits,
    load_ai_job_contract,
)
from core.ai_findings import AiFinding, AiFindingSeverity, validate_audit_finding, validate_finding_dict


def test_r259_evidence_outside_declared_lines_rejected(tmp_path: Path) -> None:
    """Evidence must appear in begin_line..end_line, not merely elsewhere in file."""
    path = tmp_path / "mod.py"
    source = "line1_safe\nline2_marker\nline3_eval(user)\n"
    path.write_text(source, encoding="utf-8")
    finding = AiFinding(
        finding_id="bad-span",
        severity=AiFindingSeverity.ERROR,
        confidence=0.9,
        title="wrong-line",
        message="claims line 2 but evidence is on line 3",
        file_path=str(path),
        begin_line=2,
        end_line=2,
        evidence="eval(user)",
    )
    assert (
        validate_audit_finding(
            finding,
            source=source,
            default_file=str(path),
            project_dir=str(tmp_path),
            project_files=(str(path),),
        )
        is None
    )


def test_r259_evidence_inside_declared_lines_accepted(tmp_path: Path) -> None:
    path = tmp_path / "mod.py"
    source = "line1_safe\nline2_eval(user)\nline3_tail\n"
    path.write_text(source, encoding="utf-8")
    finding = AiFinding(
        finding_id="ok-span",
        severity=AiFindingSeverity.ERROR,
        confidence=0.9,
        title="right-line",
        message="evidence matches span",
        file_path=str(path),
        begin_line=2,
        end_line=2,
        evidence="eval(user)",
    )
    ok = validate_audit_finding(
        finding,
        source=source,
        default_file=str(path),
        project_dir=str(tmp_path),
        project_files=(str(path),),
    )
    assert ok is not None
    assert ok.begin_line == 2
    assert ok.end_line == 2


def test_r259_zero_begin_line_rejected(tmp_path: Path) -> None:
    path = tmp_path / "mod.py"
    source = "eval(user)\n"
    path.write_text(source, encoding="utf-8")
    finding = AiFinding(
        finding_id="no-line",
        severity=AiFindingSeverity.WARNING,
        confidence=0.5,
        title="missing-coords",
        message="audit requires positive lines",
        file_path=str(path),
        begin_line=0,
        end_line=0,
        evidence="eval(user)",
    )
    assert (
        validate_audit_finding(
            finding,
            source=source,
            default_file=str(path),
            project_dir=str(tmp_path),
            project_files=(str(path),),
        )
        is None
    )


def test_r259_multi_line_span_contains_evidence(tmp_path: Path) -> None:
    path = tmp_path / "mod.py"
    source = "a = 1\nb = input()\neval(b)\n"
    path.write_text(source, encoding="utf-8")
    finding = AiFinding(
        finding_id="multi",
        severity=AiFindingSeverity.ERROR,
        confidence=0.8,
        title="span",
        message="evidence across lines",
        file_path=str(path),
        begin_line=2,
        end_line=3,
        evidence="input()\neval(b)",
    )
    assert (
        validate_audit_finding(
            finding,
            source=source,
            default_file=str(path),
            project_dir=str(tmp_path),
            project_files=(str(path),),
        )
        is not None
    )


def test_r259_budget_env_rejects_nan() -> None:
    with pytest.raises(AiBudgetConfigError, match="finite"):
        load_ai_budget_limits(environ={ENV_AI_MAX_COST_USD: "nan"})
    with pytest.raises(AiBudgetConfigError, match="finite"):
        load_ai_budget_limits(environ={ENV_AI_USD_PER_1K_TOKENS: "NaN"})


def test_r259_budget_env_rejects_infinity() -> None:
    with pytest.raises(AiBudgetConfigError, match="finite"):
        load_ai_budget_limits(environ={ENV_AI_MAX_COST_USD: "inf"})
    with pytest.raises(AiBudgetConfigError, match="finite"):
        load_ai_job_contract(environ={"CDM_AI_DEADLINE_SEC": "-inf"})


def test_r259_budget_limits_reject_nonfinite_kwargs() -> None:
    with pytest.raises(ValueError, match="finite"):
        AiBudgetLimits(max_tokens=10, max_cost_usd=math.nan, usd_per_1k_tokens=0.0)
    with pytest.raises(ValueError, match="finite"):
        AiBudgetLimits(max_tokens=10, max_cost_usd=1.0, usd_per_1k_tokens=math.inf)
    with pytest.raises(ValueError, match="finite"):
        AiJobContract(limits=AiBudgetLimits(), deadline_monotonic=math.nan)


def test_r259_finding_confidence_rejects_nan() -> None:
    assert (
        validate_finding_dict(
            {
                "title": "t",
                "message": "m",
                "severity": "warning",
                "confidence": "nan",
            }
        )
        is None
    )
