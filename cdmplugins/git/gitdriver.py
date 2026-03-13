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


def repo_spec_to_clone_url(spec: str) -> str | None:
    """Convert repo spec to git clone URL. Returns None if invalid."""
    spec = spec.strip()
    if not spec:
        return None
    if spec.startswith("http://") or spec.startswith("https://") or spec.startswith("git@"):
        return spec if spec.endswith(".git") else spec + ".git"
    try:
        from .githubapi import _parse_repo_spec

        pair = _parse_repo_spec(spec)
        if pair:
            return f"https://github.com/{pair[0]}/{pair[1]}.git"
    except ImportError:
        if "/" in spec:
            parts = spec.split("/", 1)
            if len(parts) == 2:
                return f"https://github.com/{parts[0]}/{parts[1].removesuffix('.git')}.git"
    return None


def clone_repo(repo_spec: str, target_dir: str, timeout: int = 120) -> tuple[bool, str, str | None]:
    """Clone repository to target_dir.

    target_dir: full path where the repo will be cloned (e.g. /home/user/Projects/repo_name).
    If target_dir already exists and contains .git, returns success (no clone).
    Returns:
        (success, error_message, cloned_path)
        cloned_path is the directory containing the repo, with trailing sep.
    """
    url = repo_spec_to_clone_url(repo_spec)
    if not url:
        return False, "Invalid repository address.", None

    target_dir = target_dir.rstrip(os.sep)
    if os.path.isdir(target_dir) and os.path.isdir(os.path.join(target_dir, ".git")):
        return True, "", target_dir + os.sep

    parent = os.path.dirname(target_dir)
    repo_name = os.path.basename(target_dir)
    if not repo_name:
        repo_name = url.rstrip("/").rstrip(".git").split("/")[-1]

    if not os.path.isdir(parent):
        try:
            os.makedirs(parent, exist_ok=True)
        except OSError as e:
            return False, f"Cannot create directory: {e}", None

    stdout, stderr, code = run_git(parent, ["clone", url, repo_name], timeout=timeout)
    if code != 0:
        return False, stderr.strip() or stdout.strip() or f"git clone failed (code {code})", None

    cloned = os.path.join(parent, repo_name)
    if not cloned.endswith(os.sep):
        cloned = cloned + os.sep
    return True, "", cloned


def find_cdm3_in_dir(dir_path: str) -> str | None:
    """Find first .cdm3 file in directory (non-recursive). Returns path or None."""
    dir_path = dir_path.rstrip(os.sep) + os.sep
    if not os.path.isdir(dir_path):
        return None
    for name in os.listdir(dir_path):
        if name.endswith(".cdm3") and os.path.isfile(os.path.join(dir_path, name)):
            return os.path.join(dir_path, name)
    return None
