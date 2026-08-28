# -*- coding: utf-8 -*-
"""R182: MCP backend auth + headless tool handlers (optional SDK smoke)."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from mcp_backend import tools
from mcp_backend.auth import (
    MCP_TOKEN_ENV,
    AuthError,
    require_startup_token,
    tokens_match,
    verify_call_token,
)
from mcp_backend.session import WorkspaceSession

ROOT = Path(__file__).resolve().parents[1]
CODIM = ROOT / "codimension"


def test_require_startup_token_fail_closed() -> None:
    """Missing / blank CDM_MCP_TOKEN raises AuthError."""
    with pytest.raises(AuthError):
        require_startup_token({})
    with pytest.raises(AuthError):
        require_startup_token({MCP_TOKEN_ENV: ""})
    with pytest.raises(AuthError):
        require_startup_token({MCP_TOKEN_ENV: "   "})


def test_require_startup_token_accepts_value() -> None:
    """Non-empty token is returned stripped of surrounding whitespace only at edges via strip."""
    assert require_startup_token({MCP_TOKEN_ENV: "secret-token"}) == "secret-token"


def test_tokens_match_constant_time_api() -> None:
    """Optional per-call token check uses compare_digest semantics."""
    assert tokens_match("abc", "abc") is True
    assert tokens_match("abc", "abd") is False
    assert tokens_match("abc", None) is False
    with pytest.raises(AuthError):
        verify_call_token("abc", "wrong")


def test_workspace_tools_on_tmp_project(tmp_path: Path) -> None:
    """open → list → symbols → lookup → cfg → explain → taint on a tiny tree."""
    src = tmp_path / "mod.py"
    src.write_text(
        "def greet(name):\n    return name\n\ndef bad(cmd):\n    import os\n    os.system(cmd)\n",
        encoding="utf-8",
    )
    session = WorkspaceSession()
    summary = tools.open_workspace(session, str(tmp_path))
    assert summary["file_count"] == 1
    assert summary["symbol_count"] >= 2

    listed = tools.list_project_files(session)
    assert "mod.py" in listed["files"]

    symbols = tools.get_symbols(session)
    names = {s["name"] for s in symbols["symbols"]}
    assert "greet" in names
    assert "bad" in names

    looked = tools.lookup_symbol(session, "greet")
    assert looked["definitions"]
    assert looked["definitions"][0]["name"] == "greet"

    cfg = tools.get_cfg(session, "mod.py")
    assert cfg["nodes"]
    assert cfg["entry_id"]

    explained = tools.explain_symbol(session, "greet")
    assert explained["symbol"]["name"] == "greet"
    assert "source_excerpt" in explained

    taint = tools.analyze_taint(session, "mod.py", function="bad")
    assert taint["function"] == "bad"
    assert taint["heuristic"] is True
    assert taint["findings"]


def test_path_escape_rejected(tmp_path: Path) -> None:
    """CFG/taint refuse paths outside the open workspace."""
    (tmp_path / "ok.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    outside = tmp_path.parent / "outside_r182.py"
    outside.write_text("def g():\n    return 2\n", encoding="utf-8")
    session = WorkspaceSession()
    tools.open_workspace(session, str(tmp_path))
    with pytest.raises(PermissionError):
        tools.get_cfg(session, str(outside))


def test_cli_exits_without_token() -> None:
    """``python -m mcp_backend.server`` exits non-zero when token unset."""
    env = {k: v for k, v in os.environ.items() if k != MCP_TOKEN_ENV}
    env["PYTHONPATH"] = str(CODIM) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-m", "mcp_backend.server"],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
        timeout=15,
    )
    assert proc.returncode == 1
    assert MCP_TOKEN_ENV in proc.stderr


@pytest.mark.skipif(
    importlib.util.find_spec("mcp") is None,
    reason="optional mcp SDK not installed",
)
def test_build_server_registers_tools() -> None:
    """When SDK is present, build_server exposes the MVP tool set."""
    import asyncio

    from mcp_backend.server import build_server

    server = build_server(WorkspaceSession())
    listed = asyncio.run(server.list_tools())
    tools_list = getattr(listed, "tools", listed)
    names = {getattr(tool, "name", str(tool)) for tool in tools_list}
    expected = {
        "open_workspace",
        "list_project_files",
        "get_symbols",
        "lookup_symbol",
        "get_cfg",
        "explain_symbol",
        "analyze_taint",
    }
    assert expected <= names, f"missing tools: {expected - names}; got {names}"


def test_serializers_json_roundtrip_shape(tmp_path: Path) -> None:
    """Tool payloads must be JSON-serializable."""
    (tmp_path / "x.py").write_text("def h():\n    return 0\n", encoding="utf-8")
    session = WorkspaceSession()
    tools.open_workspace(session, str(tmp_path))
    payload = tools.get_symbols(session)
    json.dumps(payload)
