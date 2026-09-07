# -*- coding: utf-8 -*-
"""R241: AI hard budgets, cancellation, and audit finding validation."""

from __future__ import annotations

from pathlib import Path

import pytest
from core.ai_budget import (
    ENV_AI_MAX_TOKENS,
    AiBudgetConfigError,
    AiBudgetExceeded,
    AiBudgetLimits,
    AiBudgetTracker,
    AiJobContract,
    load_ai_budget_limits,
    load_ai_job_contract,
)
from core.ai_config import PROVIDER_OPENAI, AiConfig
from core.ai_findings import (
    AiFinding,
    AiFindingSeverity,
    dedupe_findings,
    validate_audit_finding,
    validate_finding_dict,
)
from core.ai_http import HttpChatBackend
from core.ai_tasks import (
    AiTaskCancelled,
    AiTaskKind,
    AiTaskRequest,
    execute_ai_task,
)


def test_r241_invalid_env_fail_closed() -> None:
    with pytest.raises(AiBudgetConfigError, match="CDM_AI_MAX_TOKENS"):
        load_ai_budget_limits(environ={ENV_AI_MAX_TOKENS: "nope"})


def test_r241_record_hard_rejects_over_budget() -> None:
    tracker = AiBudgetTracker(limits=AiBudgetLimits(max_tokens=100, max_cost_usd=10.0, usd_per_1k_tokens=0.0))
    tracker.record(40, 40, hard=True)
    with pytest.raises(AiBudgetExceeded):
        tracker.record(40, 40, hard=True)


def test_r241_remaining_output_tokens_respects_cap() -> None:
    tracker = AiBudgetTracker(limits=AiBudgetLimits(max_tokens=1_000, max_cost_usd=10.0, usd_per_1k_tokens=0.0))
    assert tracker.remaining_output_tokens(100, cap=50) == 50
    assert tracker.remaining_output_tokens(980, cap=100) == 20


def test_r241_job_contract_deadline() -> None:
    limits = AiBudgetLimits(max_tokens=1000, max_cost_usd=1.0)
    contract = AiJobContract(limits=limits, deadline_monotonic=10.0)
    assert contract.deadline_exceeded(now=9.0) is False
    assert contract.deadline_exceeded(now=10.0) is True
    loaded = load_ai_job_contract(
        environ={"CDM_AI_DEADLINE_SEC": "30", "CDM_AI_MAX_FILES": "3"},
        limits=limits,
        now=100.0,
    )
    assert loaded.max_files == 3
    assert loaded.deadline_monotonic == pytest.approx(130.0)


def test_r241_dedupe_rekeys_colliding_ids() -> None:
    a = validate_finding_dict(
        {
            "finding_id": "same",
            "title": "One",
            "message": "first",
            "severity": "warning",
            "confidence": 0.5,
            "file_path": "a.py",
            "begin_line": 1,
            "evidence": "x",
        }
    )
    b = validate_finding_dict(
        {
            "finding_id": "same",
            "title": "Two",
            "message": "second",
            "severity": "warning",
            "confidence": 0.5,
            "file_path": "a.py",
            "begin_line": 2,
            "evidence": "y",
        }
    )
    assert a is not None and b is not None
    out = dedupe_findings([a, b])
    assert len(out) == 2
    assert out[0].finding_id == "same"
    assert out[1].finding_id != "same"


def test_r241_audit_finding_requires_evidence_and_path(tmp_path: Path) -> None:
    path = tmp_path / "mod.py"
    source = "def risky():\n    eval(user)\n"
    path.write_text(source, encoding="utf-8")
    files = (str(path),)
    base = AiFinding(
        finding_id="1",
        severity=AiFindingSeverity.ERROR,
        confidence=0.9,
        title="eval",
        message="bad",
        file_path=str(path),
        begin_line=2,
        end_line=2,
        evidence="",
    )
    assert (
        validate_audit_finding(
            base, source=source, default_file=str(path), project_dir=str(tmp_path), project_files=files
        )
        is None
    )
    ok = validate_audit_finding(
        AiFinding(
            finding_id="2",
            severity=AiFindingSeverity.ERROR,
            confidence=0.9,
            title="eval",
            message="bad",
            file_path=str(path),
            begin_line=2,
            end_line=2,
            evidence="eval(user)",
        ),
        source=source,
        default_file=str(path),
        project_dir=str(tmp_path),
        project_files=files,
    )
    assert ok is not None
    assert "eval(user)" in ok.evidence


def test_r241_analyze_project_cancels(tmp_path: Path) -> None:
    files: list[str] = []
    for name in ("a.py", "b.py"):
        path = tmp_path / name
        path.write_text("def f():\n    return 1\n", encoding="utf-8")
        files.append(str(path))

    calls = {"n": 0}

    def complete(system: str, user: str, *, max_output_tokens: int | None = None) -> str:
        calls["n"] += 1
        return '{"findings":[]}'

    with pytest.raises(AiTaskCancelled):
        execute_ai_task(
            AiTaskRequest(
                kind=AiTaskKind.ANALYZE_PROJECT,
                title="proj",
                project_files=tuple(files),
                project_dir=str(tmp_path),
            ),
            complete,
            backend_name="fake",
            budget_limits=AiBudgetLimits(max_tokens=100_000, max_cost_usd=10.0),
            should_cancel=lambda: True,
        )


def test_r241_analyze_project_passes_output_cap(tmp_path: Path) -> None:
    path = tmp_path / "only.py"
    path.write_text("def ok():\n    return 0\n", encoding="utf-8")
    seen: list[int | None] = []

    def complete(system: str, user: str, *, max_output_tokens: int | None = None) -> str:
        seen.append(max_output_tokens)
        if "Synthesize" in user or "Synthesize a full-project" in user:
            return "ok"
        return '{"findings":[]}'

    contract = load_ai_job_contract(
        limits=AiBudgetLimits(max_tokens=100_000, max_cost_usd=10.0),
        environ={"CDM_AI_MAX_OUTPUT_TOKENS": "123"},
    )
    execute_ai_task(
        AiTaskRequest(
            kind=AiTaskKind.ANALYZE_PROJECT,
            title="proj",
            project_files=(str(path),),
            project_dir=str(tmp_path),
        ),
        complete,
        backend_name="fake",
        job_contract=contract,
    )
    assert seen
    assert all(token == 123 or (token is not None and token <= 123) for token in seen)


def test_r241_http_backend_includes_max_tokens_in_payload() -> None:
    captured: dict[str, object] = {}

    class _Resp:
        status = 200

        def __init__(self) -> None:
            self._raw = b'{"choices":[{"message":{"content":"hi"}}]}'
            self._offset = 0

        def read(self, size: int = -1) -> bytes:
            if size is None or size < 0:
                chunk = self._raw[self._offset :]
                self._offset = len(self._raw)
                return chunk
            end = self._offset + size
            chunk = self._raw[self._offset : end]
            self._offset = end
            return chunk

        def getcode(self) -> int:
            return 200

        def geturl(self) -> str:
            return "https://api.openai.com/v1/chat/completions"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def opener(request, timeout=None):  # noqa: ANN001
        import json as _json

        captured["body"] = _json.loads(request.data.decode("utf-8"))
        return _Resp()

    backend = HttpChatBackend(
        AiConfig(provider=PROVIDER_OPENAI, model="gpt-test", base_url="https://api.openai.com/v1"),
        api_key="sk-test",
        opener=opener,
        max_output_tokens=77,
    )
    text = backend.complete("sys", "user", max_output_tokens=55)
    assert text == "hi"
    assert captured["body"]["max_tokens"] == 55
