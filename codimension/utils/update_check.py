# -*- coding: utf-8 -*-
#
# codimension - GitHub Releases update check (R172)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Read-only check for newer GitHub Releases (R172).

Fetches the public Releases API for the fork repo, compares tags to the
installed ``cdmverspec.version``, and reports whether a newer release exists.
No download or apply — that is R173+. Network access is injectable for tests.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Sequence

import cdmverspec
from packaging.version import InvalidVersion, Version

#: Default GitHub owner/repo for this fork.
DEFAULT_OWNER_REPO = "sesquicadaver/codimension"

#: Releases list endpoint (paginated by GitHub; first page is enough for tip).
DEFAULT_RELEASES_URL = f"https://api.github.com/repos/{DEFAULT_OWNER_REPO}/releases"

#: HTTP timeout for the read-only check (seconds).
DEFAULT_TIMEOUT = 10

#: Env override for the Releases API URL (tests / mirrors).
RELEASES_URL_ENV = "CDM_UPDATE_RELEASES_URL"

FetchFn = Callable[[str], bytes]


@dataclass(frozen=True)
class ReleaseInfo:
    """One non-draft GitHub release of interest."""

    tag_name: str
    version: str
    prerelease: bool
    html_url: str
    published_at: Optional[str] = None


@dataclass(frozen=True)
class UpdateCheckResult:
    """Outcome of a read-only update check."""

    status: str  # "up_to_date" | "update_available" | "error"
    current_version: str
    channel: str
    latest: Optional[ReleaseInfo] = None
    message: str = ""
    error: Optional[str] = None


def normalize_version_tag(tag: str) -> Optional[str]:
    """Strip a leading ``v``/``V`` and validate as a PEP 440 version string."""
    raw = (tag or "").strip()
    if not raw:
        return None
    if raw[:1] in ("v", "V") and len(raw) > 1 and raw[1].isdigit():
        raw = raw[1:]
    try:
        Version(raw)
    except InvalidVersion:
        return None
    return raw


def parse_release_item(item: Mapping[str, Any]) -> Optional[ReleaseInfo]:
    """Parse one GitHub release JSON object; skip drafts and unparseable tags."""
    if bool(item.get("draft")):
        return None
    tag = str(item.get("tag_name") or "")
    version = normalize_version_tag(tag)
    if version is None:
        return None
    html_url = str(item.get("html_url") or "").strip()
    published = item.get("published_at")
    published_at = str(published) if published else None
    return ReleaseInfo(
        tag_name=tag,
        version=version,
        prerelease=bool(item.get("prerelease")),
        html_url=html_url,
        published_at=published_at,
    )


def parse_releases_payload(payload: Any) -> list[ReleaseInfo]:
    """Parse a GitHub Releases JSON list into :class:`ReleaseInfo` rows."""
    if not isinstance(payload, list):
        raise ValueError("GitHub Releases payload must be a JSON array")
    out: list[ReleaseInfo] = []
    for item in payload:
        if not isinstance(item, Mapping):
            continue
        info = parse_release_item(item)
        if info is not None:
            out.append(info)
    return out


def release_allowed_for_channel(info: ReleaseInfo, channel: str) -> bool:
    """Whether a release is visible for the given release channel.

    ``stable`` ignores prereleases; ``beta`` / ``dev`` include them.
    """
    ch = cdmverspec.normalize_release_channel(channel)
    if ch == "stable":
        return not info.prerelease
    return True


def select_newer_release(
    releases: Sequence[ReleaseInfo],
    current_version: str,
    channel: str,
) -> Optional[ReleaseInfo]:
    """Return the newest allowed release strictly newer than ``current_version``."""
    try:
        current = Version(current_version)
    except InvalidVersion as exc:
        raise ValueError(f"invalid current version: {current_version!r}") from exc

    best: Optional[ReleaseInfo] = None
    best_ver: Optional[Version] = None
    for info in releases:
        if not release_allowed_for_channel(info, channel):
            continue
        try:
            ver = Version(info.version)
        except InvalidVersion:
            continue
        if ver <= current:
            continue
        if best_ver is None or ver > best_ver:
            best = info
            best_ver = ver
    return best


def default_fetch(url: str, *, timeout: float = DEFAULT_TIMEOUT) -> bytes:
    """Fetch ``url`` with urllib and a Codimension User-Agent."""
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"codimension-update-check/{cdmverspec.version}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        return body if isinstance(body, bytes) else bytes(body)


def resolve_releases_url(environ: Optional[Mapping[str, str]] = None) -> str:
    """Resolve the Releases API URL (env override or default)."""
    env: Mapping[str, str] = environ if environ is not None else os.environ
    override = env.get(RELEASES_URL_ENV)
    if override is not None and str(override).strip():
        return str(override).strip()
    return DEFAULT_RELEASES_URL


def format_update_message(result: UpdateCheckResult) -> str:
    """Human-readable summary for a dialog or log line."""
    if result.status == "error":
        return result.error or result.message or "Update check failed."
    if result.status == "update_available" and result.latest is not None:
        latest = result.latest
        extra = " (prerelease)" if latest.prerelease else ""
        return (
            f"A newer release is available: {latest.tag_name}{extra}\n"
            f"Installed: {result.current_version} ({result.channel})\n"
            f"{latest.html_url}"
        )
    return f"You are up to date: {result.current_version} ({result.channel})."


def check_for_updates(
    current_version: Optional[str] = None,
    channel: Optional[str] = None,
    *,
    fetch: Optional[FetchFn] = None,
    environ: Optional[Mapping[str, str]] = None,
    releases_url: Optional[str] = None,
) -> UpdateCheckResult:
    """Check GitHub Releases for a newer tag (read-only).

    Parameters
    ----------
    current_version:
        Installed version; defaults to ``cdmverspec.version``.
    channel:
        Release channel; defaults to ``cdmverspec.get_release_channel``.
    fetch:
        Injectable ``url -> bytes`` (mocked in tests). Defaults to HTTPS GET.
    environ:
        Optional env mapping for channel / URL overrides.
    releases_url:
        Explicit Releases API URL; else env / default.
    """
    ver = (current_version if current_version is not None else cdmverspec.version).strip()
    ch = (
        cdmverspec.normalize_release_channel(channel)
        if channel is not None
        else cdmverspec.get_release_channel(environ=environ)
    )
    url = releases_url if releases_url is not None else resolve_releases_url(environ)
    fetch_fn = fetch if fetch is not None else default_fetch

    try:
        raw = fetch_fn(url)
        payload = json.loads(raw.decode("utf-8"))
        releases = parse_releases_payload(payload)
        newer = select_newer_release(releases, ver, ch)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        result = UpdateCheckResult(
            status="error",
            current_version=ver,
            channel=ch,
            message="Network error during update check.",
            error=str(exc),
        )
        return result
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        result = UpdateCheckResult(
            status="error",
            current_version=ver,
            channel=ch,
            message="Invalid update-check response.",
            error=str(exc),
        )
        return result

    if newer is None:
        result = UpdateCheckResult(
            status="up_to_date",
            current_version=ver,
            channel=ch,
            message=f"Up to date: {ver} ({ch}).",
        )
        return result

    result = UpdateCheckResult(
        status="update_available",
        current_version=ver,
        channel=ch,
        latest=newer,
        message=f"Update available: {newer.tag_name}",
    )
    return result


__all__ = [
    "DEFAULT_OWNER_REPO",
    "DEFAULT_RELEASES_URL",
    "DEFAULT_TIMEOUT",
    "RELEASES_URL_ENV",
    "ReleaseInfo",
    "UpdateCheckResult",
    "check_for_updates",
    "default_fetch",
    "format_update_message",
    "normalize_version_tag",
    "parse_release_item",
    "parse_releases_payload",
    "release_allowed_for_channel",
    "resolve_releases_url",
    "select_newer_release",
]
