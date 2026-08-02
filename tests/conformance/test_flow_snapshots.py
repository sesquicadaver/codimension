# -*- coding: utf-8 -*-
"""T005 — golden CFG snapshot harness for flow_ast.

Baseline snapshots capture *current* parser behaviour. Span/grammar fixes
(T020+) must regenerate snapshots intentionally via::

    UPDATE_FLOW_SNAPSHOTS=1 .venv/bin/pytest tests/conformance/test_flow_snapshots.py -q
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from tests.conformance.flow_serialize import serialize_control_flow

CASES_DIR = Path(__file__).resolve().parent / "cases"
SNAPSHOTS_DIR = Path(__file__).resolve().parent / "snapshots"
UPDATE = os.environ.get("UPDATE_FLOW_SNAPSHOTS") == "1"

# Cases that need Python newer than the runner (skip load + snapshot).
_SKIP_ON_OLD = {
    "except_star.py": (3, 11),
}


def _case_files() -> list[Path]:
    return sorted(p for p in CASES_DIR.glob("*.py") if p.is_file())


def _snapshot_path(case_path: Path) -> Path:
    return SNAPSHOTS_DIR / f"{case_path.stem}.json"


@pytest.fixture(scope="module", autouse=True)
def _ensure_snapshots_dir() -> None:
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)


@pytest.mark.parametrize("case_path", _case_files(), ids=lambda p: p.name)
def test_flow_snapshot(case_path: Path) -> None:
    """Compare serialized CFG against golden JSON (or write if UPDATE_FLOW_SNAPSHOTS=1)."""
    min_ver = _SKIP_ON_OLD.get(case_path.name)
    if min_ver and sys.version_info < min_ver:
        pytest.skip(f"{case_path.name} requires Python {min_ver[0]}.{min_ver[1]}+")

    source = case_path.read_text(encoding="utf-8")
    actual = serialize_control_flow(source)
    snap = _snapshot_path(case_path)

    if UPDATE or not snap.exists():
        snap.write_text(
            json.dumps(actual, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if not UPDATE and not snap.exists():
            pytest.fail(f"missing snapshot written for first run: {snap.name}")
        if UPDATE:
            return

    expected = json.loads(snap.read_text(encoding="utf-8"))
    assert actual == expected, (
        f"CFG snapshot drift for {case_path.name}. "
        "If intentional, re-run with UPDATE_FLOW_SNAPSHOTS=1"
    )


def test_snapshot_inventory_matches_cases() -> None:
    """Every loadable case should have a snapshot file after harness bootstrap."""
    for case_path in _case_files():
        min_ver = _SKIP_ON_OLD.get(case_path.name)
        if min_ver and sys.version_info < min_ver:
            continue
        snap = _snapshot_path(case_path)
        assert snap.is_file(), f"missing snapshot for {case_path.name}: {snap}"
