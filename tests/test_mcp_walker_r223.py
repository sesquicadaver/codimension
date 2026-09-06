# -*- coding: utf-8 -*-
"""R223: MCP budget-aware workspace walker (in-walk limits + chunked reads)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from mcp_backend import tools
from mcp_backend.policy import ResourceBudgetError, WorkspacePolicy
from mcp_backend.session import WorkspaceSession
from mcp_backend.walker import _READ_CHUNK_BYTES, walk_workspace_sources


def _session(root: Path, **kwargs: Any) -> WorkspaceSession:
    return WorkspaceSession(policy=WorkspacePolicy(allowed_root=str(root), **kwargs))


def test_r223_open_workspace_uses_walker_not_full_scan(tmp_path: Path) -> None:
    """R223: open_workspace walks via walker; does not call scan_project_files."""
    import inspect

    from mcp_backend import session as session_mod

    src = inspect.getsource(session_mod.WorkspaceSession.open_workspace)
    assert "walk_workspace_sources" in src
    assert "scan_project_files" not in src
    (tmp_path / "a.py").write_text("a=1\n", encoding="utf-8")
    summary = tools.open_workspace(_session(tmp_path), str(tmp_path))
    assert summary["file_count"] == 1


def test_r223_declared_size_rejects_before_body_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """R223: st_size over remaining budget fails closed without reading the body."""
    target = tmp_path / "big.py"
    target.write_text("x=1\n", encoding="utf-8")
    opened: list[str] = []
    real_open = open

    def _tracking_open(path: Any, *args: Any, **kwargs: Any) -> Any:
        opened.append(str(path))
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", _tracking_open)
    with pytest.raises(ResourceBudgetError, match="declared size"):
        walk_workspace_sources(
            str(tmp_path),
            WorkspacePolicy(allowed_root=str(tmp_path), max_bytes=1),
        )
    assert not any(str(target) in p or p.endswith("big.py") for p in opened)


def test_r223_chunked_read_stops_mid_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """R223: when st_size under-reports, chunked read still enforces the byte budget."""
    payload = ("x" * (_READ_CHUNK_BYTES + 100)) + "\n"
    target = tmp_path / "wide.py"
    target.write_text(payload, encoding="utf-8")
    real_lstat = os.lstat

    def _underreport(path: Any, *args: Any, **kwargs: Any) -> os.stat_result:
        st = real_lstat(path, *args, **kwargs)
        if os.path.basename(str(path)) == "wide.py":
            return os.stat_result(
                (
                    st.st_mode,
                    st.st_ino,
                    st.st_dev,
                    st.st_nlink,
                    st.st_uid,
                    st.st_gid,
                    0,  # lie about size so declared-size check does not fire first
                    st.st_atime,
                    st.st_mtime,
                    st.st_ctime,
                )
            )
        return st

    monkeypatch.setattr(os, "lstat", _underreport)
    with pytest.raises(ResourceBudgetError, match="while reading"):
        walk_workspace_sources(
            str(tmp_path),
            WorkspacePolicy(allowed_root=str(tmp_path), max_bytes=_READ_CHUNK_BYTES),
        )


def test_r223_depth_prune_skips_listing_deep_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """R223: directories at max_depth are not descended into."""
    (tmp_path / "top.py").write_text("t=1\n", encoding="utf-8")
    deep = tmp_path / "d1" / "d2" / "d3"
    deep.mkdir(parents=True)
    (deep / "deep.py").write_text("d=1\n", encoding="utf-8")

    listed: list[str] = []
    real_listdir = os.listdir

    def _spy(path: Any) -> list[str]:
        listed.append(os.path.realpath(str(path)))
        return list(real_listdir(path))

    monkeypatch.setattr(os, "listdir", _spy)
    result = walk_workspace_sources(
        str(tmp_path),
        WorkspacePolicy(allowed_root=str(tmp_path), max_depth=2),
    )
    assert any(p.endswith("top.py") for p in result.sources)
    assert not any(p.endswith("deep.py") for p in result.sources)
    deep_real = os.path.realpath(deep)
    assert deep_real not in listed
