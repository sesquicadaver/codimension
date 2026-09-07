# -*- coding: utf-8 -*-
"""R231: structured AI findings + global token/cost budgets."""

from __future__ import annotations

import json
from pathlib import Path

from core.ai_budget import (
    ENV_AI_MAX_TOKENS,
    AiBudgetLimits,
    AiBudgetTracker,
    estimate_tokens,
    load_ai_budget_limits,
)
from core.ai_findings import (
    AiFindingSeverity,
    dedupe_findings,
    findings_to_sarif,
    parse_findings_payload,
    validate_finding_dict,
)
from core.ai_tasks import AiTaskKind, AiTaskRequest, execute_ai_task


def test_validate_finding_rejects_bad_confidence() -> None:
    assert validate_finding_dict({"title": "t", "message": "m", "confidence": 1.5}) is None
    assert validate_finding_dict({"title": "t", "message": "m", "severity": "nope"}) is None
    ok = validate_finding_dict(
        {
            "title": "Risky eval",
            "message": "eval on user input",
            "severity": "error",
            "confidence": 0.9,
            "file_path": "a.py",
            "begin_line": 3,
            "evidence": "eval(x)",
            "rule_id": "ai.eval",
        }
    )
    assert ok is not None
    assert ok.severity is AiFindingSeverity.ERROR
    assert ok.begin_line == 3


def test_parse_findings_from_fenced_json() -> None:
    text = (
        "Here you go:\n"
        "```json\n"
        '{"findings":[{"title":"Dup","message":"unused","severity":"warning","confidence":0.6}]}\n'
        "```\n"
    )
    findings = parse_findings_payload(text, default_file="m.py")
    assert len(findings) == 1
    assert findings[0].file_path == "m.py"
    assert findings[0].title == "Dup"


def test_dedupe_and_sarif() -> None:
    payload = {
        "findings": [
            {
                "finding_id": "same",
                "title": "A",
                "message": "m",
                "severity": "note",
                "confidence": 0.5,
                "file_path": "x.py",
                "begin_line": 1,
            },
            {
                "finding_id": "same",
                "title": "A",
                "message": "m",
                "severity": "note",
                "confidence": 0.5,
                "file_path": "x.py",
                "begin_line": 1,
            },
        ]
    }
    findings = dedupe_findings(parse_findings_payload(json.dumps(payload)))
    assert len(findings) == 1
    from core.ai_findings import AiFindingsReport

    report = AiFindingsReport(findings=findings, tokens_used=10, cost_usd=0.01)
    sarif = findings_to_sarif(report)
    assert sarif["version"] == "2.1.0"
    assert len(sarif["runs"][0]["results"]) == 1


def test_budget_tracker_blocks_when_exhausted() -> None:
    tracker = AiBudgetTracker(limits=AiBudgetLimits(max_tokens=100, max_cost_usd=10.0, usd_per_1k_tokens=0.0))
    assert tracker.can_afford(40, 40) is True
    tracker.record(40, 40)
    assert tracker.can_afford(40, 40) is False
    assert estimate_tokens("abcd") == 1


def test_load_budget_limits_from_env() -> None:
    limits = load_ai_budget_limits(environ={ENV_AI_MAX_TOKENS: "1234", "CDM_AI_MAX_COST_USD": "0.5"})
    assert limits.max_tokens == 1234
    assert limits.max_cost_usd == 0.5


def test_analyze_project_collects_findings_and_respects_budget(tmp_path: Path) -> None:
    files: list[str] = []
    for name in ("a.py", "b.py", "c.py"):
        path = tmp_path / name
        path.write_text(f"# {name}\ndef f():\n    return 1\n", encoding="utf-8")
        files.append(str(path))

    calls: list[str] = []

    def complete(system: str, user: str) -> str:
        calls.append(user)
        # Identify which file from the prompt
        for path in files:
            if path in user:
                return json.dumps(
                    {
                        "findings": [
                            {
                                "title": f"note-{Path(path).name}",
                                "message": "look here",
                                "severity": "info",
                                "confidence": 0.7,
                                "file_path": path,
                                "begin_line": 2,
                                "evidence": "def f",
                            }
                        ]
                    }
                )
        return "narrative synthesis ok"

    # First chunk fits (prompt + completion reserve); second does not.
    limits = AiBudgetLimits(max_tokens=2_500, max_cost_usd=10.0, usd_per_1k_tokens=0.0)
    result = execute_ai_task(
        AiTaskRequest(
            kind=AiTaskKind.ANALYZE_PROJECT,
            title="proj",
            project_files=tuple(files),
            project_dir=str(tmp_path),
        ),
        complete,
        backend_name="fake",
        budget_limits=limits,
    )
    assert result.kind is AiTaskKind.ANALYZE_PROJECT
    assert result.findings
    assert result.budget_tokens_used > 0
    assert result.budget_stopped is True
    assert "Structured findings" in result.text
    assert result.findings_report is not None
    assert 0 < result.findings_report.files_analyzed < 3


def test_analyze_project_full_budget_runs_synthesis(tmp_path: Path) -> None:
    path = tmp_path / "only.py"
    path.write_text("def ok():\n    return 0\n", encoding="utf-8")

    def complete(system: str, user: str) -> str:
        if "Synthesize" in user or "Synthesize a full-project" in user:
            return "Architecture looks fine."
        return '{"findings":[]}'

    result = execute_ai_task(
        AiTaskRequest(
            kind=AiTaskKind.ANALYZE_PROJECT,
            title="proj",
            project_files=(str(path),),
            project_dir=str(tmp_path),
        ),
        complete,
        backend_name="fake",
        budget_limits=AiBudgetLimits(max_tokens=100_000, max_cost_usd=10.0),
    )
    assert result.budget_stopped is False
    assert "Architecture looks fine." in result.text
    assert result.findings == ()
