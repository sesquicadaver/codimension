# -*- coding: utf-8 -*-
"""Recent projects list pruning (local settings hygiene)."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "codimension"))


def test_prune_recent_project_paths_keeps_existing_only():
    from utils.settings import prune_recent_project_paths

    root = Path(tempfile.mkdtemp(prefix="cdm-recent-prj-"))
    keep = root / "demo.cdm3"
    keep.write_text("{}", encoding="utf-8")
    missing = str(root / "gone.cdm3")
    pruned = prune_recent_project_paths(
        [
            str(keep),
            missing,
            "/home/someone/OtherProject/OtherProject.cdm3",
            str(keep),
        ]
    )
    assert pruned == [str(keep.resolve())]


def test_filedialogs_safe_start_dir(tmp_path):
    from ui.filedialogs import _safe_start_dir

    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    file_path = nested / "x.py"
    file_path.write_text("pass\n", encoding="utf-8")
    assert _safe_start_dir(str(nested)) == str(nested.resolve())
    assert _safe_start_dir(str(file_path)) == str(nested.resolve())
    assert os.path.isdir(_safe_start_dir("/no/such/path/ever"))
