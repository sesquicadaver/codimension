# -*- coding: utf-8 -*-
"""R249: AI provider output cap respects remaining token and cost budgets."""

from __future__ import annotations

from pathlib import Path

from core.ai_budget import AiBudgetLimits, AiBudgetTracker, AiJobContract
from core.ai_tasks import AiTaskKind, AiTaskRequest, execute_ai_task


def test_r249_remaining_output_tokens_respects_cost() -> None:
    """Cost remainder can bind the output cap below the token/contract ceiling."""
    # $0.01 left, $0.002 / 1k tokens → 5000 tokens affordable total.
    tracker = AiBudgetTracker(
        limits=AiBudgetLimits(max_tokens=100_000, max_cost_usd=0.01, usd_per_1k_tokens=0.002)
    )
    # prompt 1000 → leftover from cost = 4000; contract cap 4096 → 4000.
    assert tracker.remaining_output_tokens(1000, cap=4096) == 4000
    # Token ceiling binds when cost would allow more.
    tight = AiBudgetTracker(
        limits=AiBudgetLimits(max_tokens=1500, max_cost_usd=10.0, usd_per_1k_tokens=0.002)
    )
    assert tight.remaining_output_tokens(1000, cap=4096) == 500


def test_r249_remaining_output_tokens_zero_when_cost_exhausted() -> None:
    tracker = AiBudgetTracker(
        limits=AiBudgetLimits(max_tokens=100_000, max_cost_usd=0.002, usd_per_1k_tokens=0.002)
    )
    tracker.record(1000, 0, hard=True)  # spends $0.002
    assert tracker.remaining_cost_usd() == 0.0
    assert tracker.remaining_output_tokens(10, cap=4096) == 0


def test_r249_analyze_project_passes_cost_limited_cap(tmp_path: Path) -> None:
    path = tmp_path / "only.py"
    path.write_text("def ok():\n    return 0\n", encoding="utf-8")
    seen: list[int | None] = []

    def complete(system: str, user: str, *, max_output_tokens: int | None = None) -> str:
        seen.append(max_output_tokens)
        if "Synthesize" in user or "full-project" in user:
            return "ok"
        return '{"findings":[]}'

    # $0.005 @ $0.002/1k → 2500 tokens total; well below max_output_tokens=4096.
    contract = AiJobContract(
        limits=AiBudgetLimits(max_tokens=100_000, max_cost_usd=0.005, usd_per_1k_tokens=0.002),
        max_output_tokens=4096,
        max_files=10,
        max_requests=10,
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
    assert all(token is not None and 0 < token < 4096 for token in seen)
    # Cost remainder binds below the contract ceiling.
    assert all(token is not None and token <= 2500 for token in seen)
