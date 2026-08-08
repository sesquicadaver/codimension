# -*- coding: utf-8 -*-
#
# codimension - headless git churn / hotspot analytics (R137)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Headless git churn / hotspot summary from ``git log`` (R137).

Qt-free report API for local repositories. An optional plugin panel can
consume :func:`format_git_analytics_report` later; this module does not
depend on the git VCS plugin UI.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence


@dataclass(frozen=True, slots=True)
class FileChurn:
    """Per-file churn aggregated from numstat lines."""

    path: str
    commits: int
    insertions: int
    deletions: int

    @property
    def churn(self) -> int:
        """Total lines touched (insertions + deletions)."""
        return self.insertions + self.deletions


@dataclass(frozen=True, slots=True)
class AuthorActivity:
    """Commit count per author email/name key."""

    author: str
    commits: int


@dataclass(frozen=True, slots=True)
class GitAnalyticsReport:
    """Repository-level churn / hotspot summary."""

    repo: str
    commit_count: int
    files: tuple[FileChurn, ...]
    authors: tuple[AuthorActivity, ...]
    hotspots: tuple[FileChurn, ...]


class GitAnalyticsError(RuntimeError):
    """Raised when git analytics cannot be produced."""


def build_git_analytics(
    repo: str | Path,
    *,
    max_commits: int = 500,
    hotspot_limit: int = 10,
    paths: Optional[Sequence[str]] = None,
) -> GitAnalyticsReport:
    """Build a churn/hotspot report for ``repo`` via ``git log --numstat``.

    ``paths`` optionally limits analysis to pathspecs (same as ``git log -- paths``).
    """
    root = Path(repo).resolve()
    if not root.is_dir():
        raise GitAnalyticsError(f"not a directory: {root}")
    if max_commits < 1:
        raise GitAnalyticsError("max_commits must be >= 1")
    if hotspot_limit < 1:
        raise GitAnalyticsError("hotspot_limit must be >= 1")

    cmd = [
        "git",
        "-C",
        str(root),
        "log",
        f"--max-count={max_commits}",
        "--numstat",
        "--pretty=format:COMMIT\t%H\t%an <%ae>",
    ]
    if paths:
        cmd.append("--")
        cmd.extend(paths)

    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            env=_git_env(),
        )
    except OSError as exc:
        raise GitAnalyticsError(f"failed to invoke git: {exc}") from exc

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
        raise GitAnalyticsError(f"git log failed: {err}")

    commit_count = 0
    author_counts: dict[str, int] = {}
    file_commits: dict[str, int] = {}
    file_ins: dict[str, int] = {}
    file_del: dict[str, int] = {}
    seen_in_commit: set[str] = set()

    for raw_line in proc.stdout.splitlines():
        line = raw_line.rstrip("\n")
        if line.startswith("COMMIT\t"):
            parts = line.split("\t", 2)
            if len(parts) < 3:
                continue
            commit_count += 1
            author = parts[2].strip() or "unknown"
            author_counts[author] = author_counts.get(author, 0) + 1
            seen_in_commit = set()
            continue
        if not line or "\t" not in line:
            continue
        cols = line.split("\t")
        if len(cols) < 3:
            continue
        ins_s, del_s, path = cols[0], cols[1], cols[2]
        if path.startswith("{") or " => " in path:
            # Rename summaries from numstat; keep the destination side when present.
            if " => " in path:
                path = path.split(" => ", 1)[-1].rstrip("}")
        if ins_s == "-" and del_s == "-":
            # Binary file
            insertions = 0
            deletions = 0
        else:
            try:
                insertions = int(ins_s)
                deletions = int(del_s)
            except ValueError:
                continue
        file_ins[path] = file_ins.get(path, 0) + insertions
        file_del[path] = file_del.get(path, 0) + deletions
        if path not in seen_in_commit:
            file_commits[path] = file_commits.get(path, 0) + 1
            seen_in_commit.add(path)

    files = tuple(
        sorted(
            (
                FileChurn(
                    path=path,
                    commits=file_commits.get(path, 0),
                    insertions=file_ins.get(path, 0),
                    deletions=file_del.get(path, 0),
                )
                for path in file_ins
            ),
            key=lambda item: (-item.churn, -item.commits, item.path),
        )
    )
    authors = tuple(
        sorted(
            (AuthorActivity(author=a, commits=c) for a, c in author_counts.items()),
            key=lambda item: (-item.commits, item.author),
        )
    )
    hotspots = files[:hotspot_limit]
    return GitAnalyticsReport(
        repo=str(root),
        commit_count=commit_count,
        files=files,
        authors=authors,
        hotspots=hotspots,
    )


def format_git_analytics_report(report: GitAnalyticsReport, *, max_hotspots: int = 10) -> str:
    """Plain-text summary suitable for a future plugin panel / CLI."""
    lines = [
        f"Git analytics: {report.repo}",
        f"Commits analyzed: {report.commit_count}",
        f"Files touched: {len(report.files)}",
        f"Authors: {len(report.authors)}",
        "",
        "Hotspots (by churn):",
    ]
    for item in report.hotspots[:max_hotspots]:
        lines.append(f"  {item.churn:6d}  +{item.insertions}/-{item.deletions}  {item.commits} commits  {item.path}")
    if not report.hotspots:
        lines.append("  (none)")
    return "\n".join(lines)


def _git_env() -> dict[str, str]:
    """Environment for non-interactive git invocations."""
    env = dict(os.environ)
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    env.setdefault("LC_ALL", "C")
    return env


__all__ = [
    "AuthorActivity",
    "FileChurn",
    "GitAnalyticsError",
    "GitAnalyticsReport",
    "build_git_analytics",
    "format_git_analytics_report",
]
