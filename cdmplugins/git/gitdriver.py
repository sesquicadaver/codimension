# -*- coding: utf-8 -*-
#
# Codimension - Python 3 experimental IDE
# Copyright (C) 2025  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Execute git commands via subprocess.

Used from getStatus (VCSPluginThread) and from UI handlers.
Uses configured git path from gitconfig.
"""

import os
import subprocess


def _git_executable():
    """Return path to git executable (from config or default)."""
    try:
        from .gitconfig import get_git_path
        return get_git_path()
    except ImportError:
        return "git"


def find_git_root(path: str) -> str | None:
    """Return path to .git root or None if not a git repo."""
    current = os.path.abspath(path)
    if os.path.isfile(current):
        current = os.path.dirname(current)
    if not current.endswith(os.path.sep):
        current = current + os.path.sep
    while True:
        if os.path.isdir(os.path.join(current, ".git")):
            return current.rstrip(os.path.sep) + os.path.sep
        parent = os.path.dirname(current.rstrip(os.path.sep))
        if not parent or parent == current.rstrip(os.path.sep):
            return None
        current = parent + os.path.sep


def run_git(cwd: str, args: list[str], timeout: int = 30) -> tuple[str, str, int]:
    """Run git with args in cwd.

    Returns:
        (stdout, stderr, returncode)
    """
    try:
        result = subprocess.run(
            [_git_executable()] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return (
            result.stdout or "",
            result.stderr or "",
            result.returncode,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return ("", str(e), -1)
