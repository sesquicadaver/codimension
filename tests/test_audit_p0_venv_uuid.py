# -*- coding: utf-8 -*-
"""P0 audit: real dual-venv identity + project UUID containment."""

from __future__ import annotations

import os
import sys
import venv

import pytest


@pytest.mark.integration
def test_project_venv_not_classified_as_ide_when_symlinked_to_same_base(tmp_path):
    """Two real venvs may share realpath(python); identity must use venv roots."""
    from utils import venvbootstrap as vb

    ide_venv = tmp_path / "ide-venv"
    proj_venv = tmp_path / "proj-venv"
    venv.create(str(ide_venv), with_pip=False, symlinks=True)
    venv.create(str(proj_venv), with_pip=False, symlinks=True)

    ide_py = vb.resolveVenvToPython(str(ide_venv))
    proj_py = vb.resolveVenvToPython(str(proj_venv))
    assert ide_py and proj_py
    assert os.path.realpath(ide_py) == os.path.realpath(proj_py)

    old_prefix, old_exe = sys.prefix, sys.executable
    try:
        sys.prefix = str(ide_venv)
        sys.executable = ide_py
        assert vb.isIdePythonEnvironment(ide_py) is True
        assert vb.isIdePythonEnvironment(proj_py) is False
        assert vb.assertSafeMutableProjectPython(proj_py) == os.path.abspath(proj_py)
        with pytest.raises(RuntimeError, match="IDE"):
            vb.assertSafeMutableProjectPython(ide_py)
    finally:
        sys.prefix = old_prefix
        sys.executable = old_exe


def test_project_uuid_rejects_path_traversal(tmp_path):
    from utils.project_schema import ProjectSchemaError, safe_user_project_dir, validate_project_props

    settings = tmp_path / "settings"
    settings.mkdir()
    with pytest.raises(ProjectSchemaError, match="path|UUID|uuid"):
        safe_user_project_dir(str(settings), "../../evil")
    with pytest.raises(ProjectSchemaError):
        validate_project_props({"uuid": "../../evil"})
    with pytest.raises(ProjectSchemaError):
        validate_project_props({"uuid": "not-a-uuid"})

    good = "11111111-1111-1111-1111-111111111111"
    path = safe_user_project_dir(str(settings), good)
    settings_root = os.path.realpath(str(settings))
    assert os.path.commonpath([os.path.realpath(path), settings_root]) == settings_root
    assert good in path

    props = validate_project_props({"uuid": good})
    assert props["uuid"] == good


def test_project_uuid_canonicalizes_compact_form(tmp_path):
    from utils.project_schema import safe_user_project_dir, validate_project_props

    compact = "11111111111111111111111111111111"
    props = validate_project_props({"uuid": compact})
    assert props["uuid"] == "11111111-1111-1111-1111-111111111111"
    settings = tmp_path / "s"
    settings.mkdir()
    path = safe_user_project_dir(str(settings), compact)
    assert props["uuid"] in path
