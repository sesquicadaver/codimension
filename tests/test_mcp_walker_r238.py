# -*- coding: utf-8 -*-
"""R238: MCP fd-safe bounded traversal (scandir, entry budgets, O_NOFOLLOW)."""

from __future__ import annotations

from pathlib import Path

import pytest
from mcp_backend.policy import (
    MCP_MAX_DIRECTORIES_ENV,
    MCP_MAX_ENTRIES_ENV,
    ResourceBudgetError,
    WorkspacePolicy,
    policy_from_environ,
)
from mcp_backend.walker import walk_workspace_sources


def test_r238_max_files_raises_in_sorted_name_order(tmp_path: Path) -> None:
    """R238: scandir results are name-sorted so budgets trip deterministically."""
    (tmp_path / "c.py").write_text("c=1\n", encoding="utf-8")
    (tmp_path / "a.py").write_text("a=1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("b=1\n", encoding="utf-8")
    with pytest.raises(ResourceBudgetError, match="max_files"):
        walk_workspace_sources(
            str(tmp_path),
            WorkspacePolicy(allowed_root=str(tmp_path), max_files=2),
        )


def test_r238_max_entries_counts_non_python(tmp_path: Path) -> None:
    for i in range(5):
        (tmp_path / f"noise{i}.txt").write_text("x\n", encoding="utf-8")
    (tmp_path / "ok.py").write_text("ok=1\n", encoding="utf-8")
    with pytest.raises(ResourceBudgetError, match="max_entries"):
        walk_workspace_sources(
            str(tmp_path),
            WorkspacePolicy(allowed_root=str(tmp_path), max_entries=3),
        )


def test_r238_max_directories_budget(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "c").mkdir()
    (tmp_path / "a" / "x.py").write_text("x=1\n", encoding="utf-8")
    with pytest.raises(ResourceBudgetError, match="max_directories"):
        walk_workspace_sources(
            str(tmp_path),
            WorkspacePolicy(allowed_root=str(tmp_path), max_directories=2),
        )


def test_r238_skips_symlink_file(tmp_path: Path) -> None:
    real = tmp_path / "real.py"
    real.write_text("real=1\n", encoding="utf-8")
    link = tmp_path / "link.py"
    link.symlink_to(real)
    result = walk_workspace_sources(
        str(tmp_path),
        WorkspacePolicy(allowed_root=str(tmp_path)),
    )
    assert any(p.endswith("real.py") for p in result.sources)
    assert not any(p.endswith("link.py") for p in result.sources)


def test_r238_skips_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.py"
    secret.write_text("secret=1\n", encoding="utf-8")
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "ok.py").write_text("ok=1\n", encoding="utf-8")
    (ws / "escape").symlink_to(outside)
    result = walk_workspace_sources(
        str(ws),
        WorkspacePolicy(allowed_root=str(ws)),
    )
    assert any(p.endswith("ok.py") for p in result.sources)
    assert not any(p.endswith("secret.py") for p in result.sources)


def test_r238_policy_env_entries_directories(tmp_path: Path) -> None:
    policy = policy_from_environ(
        {
            "CDM_MCP_WORKSPACE": str(tmp_path),
            MCP_MAX_ENTRIES_ENV: "123",
            MCP_MAX_DIRECTORIES_ENV: "45",
        }
    )
    assert policy.max_entries == 123
    assert policy.max_directories == 45
