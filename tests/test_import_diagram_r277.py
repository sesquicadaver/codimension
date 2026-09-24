# -*- coding: utf-8 -*-
"""R277: import diagram must not list setuptools build/ mirrors as entry points."""

from __future__ import annotations

from pathlib import Path

from codimension.utils.project_scan import path_has_packaging_artifact


def test_r277_packaging_paths_filtered_for_diagram_participants(tmp_path: Path) -> None:
    """Mirror under project-root build/ must be filtered from diagram participants."""
    src = tmp_path / "pkg" / "telemetry_soak.py"
    src.parent.mkdir(parents=True)
    src.write_text("print(1)\n", encoding="utf-8")
    mirror = tmp_path / "build" / "lib" / "pkg" / "telemetry_soak.py"
    mirror.parent.mkdir(parents=True)
    mirror.write_text("print(1)\n", encoding="utf-8")
    nested_ok = tmp_path / "src" / "build" / "helper.py"
    nested_ok.parent.mkdir(parents=True)
    nested_ok.write_text("h = 1\n", encoding="utf-8")

    project_dir = str(tmp_path)
    assert not path_has_packaging_artifact(str(src), project_dir)
    assert path_has_packaging_artifact(str(mirror), project_dir)
    assert not path_has_packaging_artifact(str(nested_ok), project_dir)
