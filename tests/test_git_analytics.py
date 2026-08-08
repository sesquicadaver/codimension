# -*- coding: utf-8 -*-
"""R137: headless git churn / hotspot analytics."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import parsers  # noqa: E402,F401
import pytest

_CODIM = Path(__file__).resolve().parents[1] / "codimension"


@pytest.fixture(autouse=True)
def _purge_stubs():
    import importlib

    def _under(mod: object) -> bool:
        path = getattr(mod, "__file__", None)
        if path:
            return "/codimension/" in os.path.abspath(path).replace("\\", "/")
        return False

    dirty = False
    for name in list(sys.modules):
        if name not in ("ui", "utils") and not name.startswith(("ui.", "utils.")):
            continue
        if _under(sys.modules[name]):
            continue
        del sys.modules[name]
        dirty = True
    if dirty:
        importlib.invalidate_caches()
        if str(_CODIM) not in sys.path:
            sys.path.insert(0, str(_CODIM))
    yield


def _run_git(repo: Path, *args: str) -> None:
    env = dict(os.environ)
    env["GIT_AUTHOR_NAME"] = "Test Author"
    env["GIT_AUTHOR_EMAIL"] = "test@example.com"
    env["GIT_COMMITTER_NAME"] = "Test Author"
    env["GIT_COMMITTER_EMAIL"] = "test@example.com"
    env["GIT_TERMINAL_PROMPT"] = "0"
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    """Tiny git repo with uneven churn for hotspot ranking."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(repo, "init")
    _run_git(repo, "config", "user.email", "test@example.com")
    _run_git(repo, "config", "user.name", "Test Author")

    hot = repo / "hot.py"
    cold = repo / "cold.py"
    hot.write_text("print(1)\n", encoding="utf-8")
    cold.write_text("print(0)\n", encoding="utf-8")
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-m", "initial")

    for i in range(3):
        hot.write_text(hot.read_text(encoding="utf-8") + f"print({i + 2})\n", encoding="utf-8")
        _run_git(repo, "add", "hot.py")
        _run_git(repo, "commit", "-m", f"touch hot {i}")

    return repo


def test_build_git_analytics_hotspots(sample_repo: Path) -> None:
    from utils.git_analytics import build_git_analytics, format_git_analytics_report

    report = build_git_analytics(sample_repo, hotspot_limit=5)
    assert report.commit_count == 4
    assert report.authors
    assert report.authors[0].commits == 4
    by_path = {f.path: f for f in report.files}
    assert "hot.py" in by_path and "cold.py" in by_path
    assert by_path["hot.py"].churn > by_path["cold.py"].churn
    assert by_path["hot.py"].commits > by_path["cold.py"].commits
    assert report.hotspots[0].path == "hot.py"

    text = format_git_analytics_report(report)
    assert "Hotspots" in text
    assert "hot.py" in text


def test_build_git_analytics_path_filter(sample_repo: Path) -> None:
    from utils.git_analytics import build_git_analytics

    report = build_git_analytics(sample_repo, paths=["cold.py"])
    assert {f.path for f in report.files} == {"cold.py"}
    assert report.commit_count >= 1


def test_build_git_analytics_rejects_non_repo(tmp_path: Path) -> None:
    from utils.git_analytics import GitAnalyticsError, build_git_analytics

    with pytest.raises(GitAnalyticsError):
        build_git_analytics(tmp_path / "missing")
