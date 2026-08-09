# -*- coding: utf-8 -*-
"""R172: read-only GitHub Releases update check (mocked HTTP)."""

from __future__ import annotations

import json
import os
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


def _releases_json(items: list[dict]) -> bytes:
    return json.dumps(items).encode("utf-8")


def test_normalize_version_tag() -> None:
    from utils.update_check import normalize_version_tag

    assert normalize_version_tag("v4.12.0") == "4.12.0"
    assert normalize_version_tag("4.11.0") == "4.11.0"
    assert normalize_version_tag("not-a-version") is None
    assert normalize_version_tag("") is None


def test_select_newer_release_stable_skips_prerelease() -> None:
    from utils.update_check import ReleaseInfo, select_newer_release

    releases = [
        ReleaseInfo("v4.12.0-rc1", "4.12.0rc1", True, "https://example/rc"),
        ReleaseInfo("v4.11.1", "4.11.1", False, "https://example/4111"),
        ReleaseInfo("v4.10.0", "4.10.0", False, "https://example/410"),
    ]
    newer = select_newer_release(releases, "4.11.0", "stable")
    assert newer is not None
    assert newer.version == "4.11.1"
    assert select_newer_release(releases, "4.11.1", "stable") is None


def test_select_newer_release_beta_allows_prerelease() -> None:
    from utils.update_check import ReleaseInfo, select_newer_release

    releases = [
        ReleaseInfo("v4.12.0-rc1", "4.12.0rc1", True, "https://example/rc"),
        ReleaseInfo("v4.11.1", "4.11.1", False, "https://example/4111"),
    ]
    newer = select_newer_release(releases, "4.11.0", "beta")
    assert newer is not None
    assert newer.version == "4.12.0rc1"


def test_check_for_updates_available_with_mock_fetch() -> None:
    from utils.update_check import check_for_updates, format_update_message

    payload = _releases_json(
        [
            {
                "tag_name": "v4.12.0",
                "prerelease": False,
                "draft": False,
                "html_url": "https://github.com/sesquicadaver/codimension/releases/tag/v4.12.0",
                "published_at": "2026-08-01T00:00:00Z",
            },
            {
                "tag_name": "v4.11.0",
                "prerelease": False,
                "draft": False,
                "html_url": "https://github.com/sesquicadaver/codimension/releases/tag/v4.11.0",
            },
        ]
    )
    seen: list[str] = []

    def fetch(url: str) -> bytes:
        seen.append(url)
        return payload

    result = check_for_updates(
        current_version="4.11.0",
        channel="stable",
        fetch=fetch,
        releases_url="https://example.test/releases",
    )
    assert seen == ["https://example.test/releases"]
    assert result.status == "update_available"
    assert result.latest is not None
    assert result.latest.tag_name == "v4.12.0"
    msg = format_update_message(result)
    assert "v4.12.0" in msg
    assert "4.11.0" in msg


def test_check_for_updates_up_to_date() -> None:
    from utils.update_check import check_for_updates

    payload = _releases_json(
        [
            {
                "tag_name": "v4.11.0",
                "prerelease": False,
                "draft": False,
                "html_url": "https://github.com/x/y/releases/tag/v4.11.0",
            },
            {
                "tag_name": "v4.10.0",
                "prerelease": False,
                "draft": False,
                "html_url": "https://github.com/x/y/releases/tag/v4.10.0",
            },
        ]
    )
    result = check_for_updates(
        current_version="4.11.0",
        channel="stable",
        fetch=lambda _url: payload,
    )
    assert result.status == "up_to_date"
    assert result.latest is None


def test_check_for_updates_skips_drafts_and_bad_tags() -> None:
    from utils.update_check import check_for_updates

    payload = _releases_json(
        [
            {
                "tag_name": "v9.9.9",
                "prerelease": False,
                "draft": True,
                "html_url": "https://example/draft",
            },
            {
                "tag_name": "nightly",
                "prerelease": False,
                "draft": False,
                "html_url": "https://example/nightly",
            },
            {
                "tag_name": "v4.11.0",
                "prerelease": False,
                "draft": False,
                "html_url": "https://example/411",
            },
        ]
    )
    result = check_for_updates(
        current_version="4.11.0",
        channel="stable",
        fetch=lambda _url: payload,
    )
    assert result.status == "up_to_date"


def test_check_for_updates_network_error() -> None:
    from utils.update_check import check_for_updates

    def boom(_url: str) -> bytes:
        raise TimeoutError("timed out")

    result = check_for_updates(current_version="4.11.0", channel="stable", fetch=boom)
    assert result.status == "error"
    assert result.error is not None
    assert "timed out" in result.error


def test_check_for_updates_invalid_json() -> None:
    from utils.update_check import check_for_updates

    result = check_for_updates(
        current_version="4.11.0",
        channel="stable",
        fetch=lambda _url: b"not-json{",
    )
    assert result.status == "error"


def test_resolve_releases_url_env() -> None:
    from utils.update_check import DEFAULT_RELEASES_URL, RELEASES_URL_ENV, resolve_releases_url

    assert resolve_releases_url(environ={}) == DEFAULT_RELEASES_URL
    assert resolve_releases_url(environ={RELEASES_URL_ENV: " https://mirror/r "}) == "https://mirror/r"
