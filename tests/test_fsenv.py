# -*- coding: utf-8 -*-
"""Recent-files pruning for FileSystemEnvironment (pytest/tmp pollution)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "codimension"))


def _durable_tmp() -> Path:
    """Temp dir outside pytest-of-* so prune helpers do not treat it as transient."""
    return Path(tempfile.mkdtemp(prefix="cdm-fsenv-keep-"))


def test_is_transient_recent_path():
    from utils.fsenv import is_transient_recent_path

    assert is_transient_recent_path(
        "/tmp/pytest-of-sesquicadaver/pytest-428/test_mainwindow_debug_stop_at_0/dbg_target.py"
    )
    assert is_transient_recent_path("/tmp/pytest-of-u/x.py")
    assert is_transient_recent_path("/tmp/t130-script/dbg_target.py")
    assert not is_transient_recent_path("/home/u/proj/main.py")
    assert not is_transient_recent_path("/tmp/my-scratch.py")


def test_prune_recent_files_drops_missing_and_transient():
    from utils.fsenv import prune_recent_files

    root = _durable_tmp()
    keep = root / "keep.py"
    keep.write_text("x = 1\n", encoding="utf-8")
    missing = str(root / "gone.py")
    transient = "/tmp/pytest-of-x/pytest-1/dbg_target.py"
    pruned = prune_recent_files([str(keep), missing, transient, str(keep)])
    assert pruned == [str(keep)]


def test_add_recent_rejects_transient_and_missing():
    from utils.fsenv import FileSystemEnvironment

    root = _durable_tmp()
    env = FileSystemEnvironment()
    env.setup(str(root))
    assert env.addRecentFile("/tmp/pytest-of-u/pytest-1/a.py") is False
    assert env.recentFiles == []

    missing = str(root / "nope.py")
    assert env.addRecentFile(missing) is False

    keep = root / "ok.py"
    keep.write_text("pass\n", encoding="utf-8")
    assert env.addRecentFile(str(keep)) is True
    assert env.recentFiles == [str(keep)]


def test_load_prunes_stale_recent_on_disk():
    from utils.fsenv import FileSystemEnvironment

    root = _durable_tmp()
    keep = root / "ok.py"
    keep.write_text("pass\n", encoding="utf-8")
    payload = {
        "tabs": [],
        "recent": [
            "/tmp/pytest-of-u/pytest-1/dbg_target.py",
            str(root / "missing.py"),
            str(keep),
        ],
        "fsbrowserexpandeddirs": [],
        "topleveldirs": [],
    }
    (root / "fsenv.json").write_text(json.dumps(payload), encoding="utf-8")

    env = FileSystemEnvironment()
    env.setup(str(root))
    assert env.recentFiles == [str(keep)]
    disk = json.loads((root / "fsenv.json").read_text(encoding="utf-8"))
    assert disk["recent"] == [str(keep)]
