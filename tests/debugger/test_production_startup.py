# -*- coding: utf-8 -*-
"""D07/B08: production-like MainWindow bootstrap + bundled plugin load (PR blocker)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_bundled_plugin_search_paths_include_cdmplugins_package():
    """Plugin manager must locate installed ``cdmplugins`` without argv heuristics."""
    from plugins.manager.pluginmanager import bundledPluginSearchPaths

    import cdmplugins

    bundled = os.path.dirname(os.path.abspath(cdmplugins.__file__))
    paths = bundledPluginSearchPaths()
    assert bundled in paths
    assert os.path.isfile(os.path.join(bundled, "git", "git.cdmp"))


def test_mainwindow_bootstrap_loads_at_least_one_plugin():
    """Run production smoke in a subprocess so CodimensionApplication does not poison later tests."""
    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    # Prefer the repo venv interpreter that pytest is using.
    script = ROOT / "scripts" / "offscreen_gui_smoke.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"production smoke failed (rc={result.returncode})\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "plugins_active=" in result.stdout
