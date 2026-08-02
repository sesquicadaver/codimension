# -*- coding: utf-8 -*-
"""T100/T101: debugger client scripts resolve from the package tree."""

from __future__ import annotations

from pathlib import Path


def test_debugger_client_path_points_at_package_scripts():
    """``_debuggerClientPath`` must not depend on ``sys.argv[0]`` (pytest-safe)."""
    import parsers  # noqa: F401
    from utils.run import _debuggerClientPath

    dbg = Path(_debuggerClientPath("client_cdm_dbg.py"))
    run = Path(_debuggerClientPath("client_cdm_run.py"))
    profile = Path(_debuggerClientPath("client_cdm_profile.py"))
    assert dbg.is_file()
    assert run.is_file()
    assert profile.is_file()
    assert dbg.parent.name == "client"
    assert dbg.parent.parent.name == "debugger"
