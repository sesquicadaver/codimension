# -*- coding: utf-8 -*-
"""R247: MCP entry budget applied before full scandir materialize/sort."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from mcp_backend.policy import ResourceBudgetError, WorkspacePolicy
from mcp_backend.walker import bounded_sorted_scandir_entries, walk_workspace_sources


class _CountingScanner:
    """Iterator that counts how many entries were pulled from scandir."""

    def __init__(self, names: list[str]) -> None:
        self.names = list(names)
        self.pulled = 0

    def __iter__(self) -> Iterator[object]:
        return self

    def __next__(self) -> object:
        if self.pulled >= len(self.names):
            raise StopIteration
        name = self.names[self.pulled]
        self.pulled += 1

        class _Entry:
            def __init__(self, entry_name: str) -> None:
                self.name = entry_name

        return _Entry(name)


def test_bounded_sorted_stops_after_remaining_plus_one() -> None:
    scanner = _CountingScanner([f"f{i:04d}.py" for i in range(1000)])
    entries = bounded_sorted_scandir_entries(scanner, remaining_budget=3)
    assert scanner.pulled == 4  # remaining + 1 sentinel, not 1000
    assert len(entries) == 4
    assert [e.name for e in entries] == ["f0000.py", "f0001.py", "f0002.py", "f0003.py"]


def test_bounded_sorted_unlimited_collects_all_and_sorts() -> None:
    scanner = _CountingScanner(["c.py", "a.py", "b.py"])
    entries = bounded_sorted_scandir_entries(scanner, remaining_budget=None)
    assert scanner.pulled == 3
    assert [e.name for e in entries] == ["a.py", "b.py", "c.py"]


def test_bounded_sorted_zero_remaining_pulls_one_sentinel() -> None:
    scanner = _CountingScanner([f"n{i}.txt" for i in range(50)])
    entries = bounded_sorted_scandir_entries(scanner, remaining_budget=0)
    assert scanner.pulled == 1
    assert len(entries) == 1


def test_r247_max_entries_raises_without_loading_huge_dir(tmp_path: Path) -> None:
    """Integration: many siblings still trip max_entries (bounded collect)."""
    for i in range(40):
        (tmp_path / f"noise{i:02d}.txt").write_text("x\n", encoding="utf-8")
    (tmp_path / "ok.py").write_text("ok=1\n", encoding="utf-8")
    with pytest.raises(ResourceBudgetError, match="max_entries"):
        walk_workspace_sources(
            str(tmp_path),
            WorkspacePolicy(allowed_root=str(tmp_path), max_entries=5),
        )
