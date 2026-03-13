# -*- coding: utf-8 -*-
"""Tests for cdmplugins.git.gitstatusparser.

Unit tests for git status --porcelain parsing. No Qt/GUI required.
Import gitstatusparser directly to avoid pulling in VersionControlSystemInterface/Qt.
"""

import importlib.util
import os.path

_spec = importlib.util.spec_from_file_location(
    "gitstatusparser",
    os.path.join(os.path.dirname(__file__), "..", "cdmplugins", "git", "gitstatusparser.py"),
)
_gitstatusparser = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gitstatusparser)

IND_ADDED = _gitstatusparser.IND_ADDED
IND_CLEAN = _gitstatusparser.IND_CLEAN
IND_CONFLICT = _gitstatusparser.IND_CONFLICT
IND_DELETED = _gitstatusparser.IND_DELETED
IND_MODIFIED = _gitstatusparser.IND_MODIFIED
IND_UNTRACKED = _gitstatusparser.IND_UNTRACKED
parse_status_output = _gitstatusparser.parse_status_output


def test_parse_empty():
    """Empty output returns empty list."""
    assert parse_status_output("/repo", "") == []
    assert parse_status_output("/repo", "\n\n") == []


def test_parse_untracked():
    """Untracked files: ?? path."""
    out = "?? newfile.py\n?? another.txt"
    result = parse_status_output("/repo/", out)
    assert len(result) == 2
    assert result[0][0] == "newfile.py"
    assert result[0][1] == IND_UNTRACKED
    assert result[1][0] == "another.txt"
    assert result[1][1] == IND_UNTRACKED


def test_parse_modified():
    """Modified: M  path."""
    out = " M modified.py\nMM staged_and_modified.py"
    result = parse_status_output("/repo/", out)
    assert len(result) == 2
    assert result[0][1] == IND_MODIFIED
    assert result[1][1] == IND_MODIFIED


def test_parse_added():
    """Added: A  path."""
    out = "A  new.py"
    result = parse_status_output("/repo/", out)
    assert len(result) == 1
    assert result[0][1] == IND_ADDED


def test_parse_deleted():
    """Deleted: D  path."""
    out = " D deleted.py"

    result = parse_status_output("/repo/", out)
    assert len(result) == 1
    assert result[0][1] == IND_DELETED


def test_parse_rename():
    """Rename: R  old -> new."""
    out = "R  oldname.py -> newname.py"
    result = parse_status_output("/repo/", out)
    assert len(result) == 1
    assert result[0][0] == "newname.py"
    assert result[0][1] == IND_MODIFIED


def test_parse_conflict():
    """Unmerged: UU, AA, DD."""
    out = "UU conflict.py\nAA both_added.py"
    result = parse_status_output("/repo/", out)
    assert len(result) == 2
    assert result[0][1] == IND_CONFLICT
    assert result[1][1] == IND_CONFLICT


def test_parse_subdir():
    """Paths in subdirectories."""
    out = "?? subdir/file.py"
    result = parse_status_output("/repo/", out)
    assert len(result) == 1
    assert result[0][0] == "subdir" + os.path.sep + "file.py"


def test_parse_git_root_trailing_sep():
    """Git root with or without trailing sep."""
    out = "?? new.py"
    r1 = parse_status_output("/repo", out)
    r2 = parse_status_output("/repo/", out)
    assert r1 == r2
    assert r1[0][0] == "new.py"
