# -*- coding: utf-8 -*-
"""Tests for default analysis artifact excludes and persist helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from codimension.utils.analysis_excludes import (
    list_default_artifact_excludes,
    merge_analysis_exclude_paths,
    persist_artifact_excludes_to_project,
)


def test_list_default_artifact_excludes_finds_build_dist_egginfo(tmp_path: Path) -> None:
    (tmp_path / "build" / "lib").mkdir(parents=True)
    (tmp_path / "dist").mkdir()
    (tmp_path / "pkg.egg-info").mkdir()
    (tmp_path / "src").mkdir()
    found = {Path(p).name for p in list_default_artifact_excludes(str(tmp_path))}
    assert "build" in found
    assert "dist" in found
    assert "pkg.egg-info" in found
    assert "src" not in found


def test_merge_analysis_exclude_paths_respects_enabled_flag(tmp_path: Path) -> None:
    (tmp_path / "build").mkdir()
    user = [str(tmp_path / "vendor")]
    (tmp_path / "vendor").mkdir()
    merged_on = merge_analysis_exclude_paths(str(tmp_path), user, enabled=True)
    assert any(Path(p).name == "build" for p in merged_on)
    assert any(Path(p).name == "vendor" for p in merged_on)
    merged_off = merge_analysis_exclude_paths(str(tmp_path), user, enabled=False)
    assert not any(Path(p).name == "build" for p in merged_off)
    assert any(Path(p).name == "vendor" for p in merged_off)


def test_persist_artifact_excludes_adds_names_and_existing_dirs(tmp_path: Path) -> None:
    (tmp_path / "build").mkdir()
    project = MagicMock()
    project.isLoaded.return_value = True
    project.getProjectDir.return_value = str(tmp_path)
    project.props = {"excludeFromAnalysis": []}

    def _update(props):
        project.props = props

    project.updateProperties.side_effect = _update
    added = persist_artifact_excludes_to_project(project)
    assert "build" in added
    assert "dist" in project.props["excludeFromAnalysis"]
    assert ".eggs" in project.props["excludeFromAnalysis"]
    # Second call is idempotent.
    added2 = persist_artifact_excludes_to_project(project)
    assert added2 == []


def test_should_offer_unresolved_import_choice(tmp_path: Path) -> None:
    from codimension.utils.unresolved_import_choice import (
        clear_unresolved_import_skip_session,
        mark_unresolved_import_skipped,
        should_offer_unresolved_import_choice,
    )

    clear_unresolved_import_skip_session()
    project = MagicMock()
    project.isLoaded.return_value = True
    project.getProjectDir.return_value = str(tmp_path)
    assert should_offer_unresolved_import_choice(project, ["native"]) is True
    assert should_offer_unresolved_import_choice(project, []) is False
    mark_unresolved_import_skipped(str(tmp_path), ["native"])
    assert should_offer_unresolved_import_choice(project, ["native"]) is False
