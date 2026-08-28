# -*- coding: utf-8 -*-
#
# codimension - release channel promotion (R181)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Tag-based release-channel promotion without branch theatre (R181).

Solo-fork model: one ``master`` line; channels are metadata + PEP 440 tag
shape, not parallel ``stable``/``develop`` branches.

Promotion order: ``dev`` → ``beta`` → ``stable`` (forward only).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cdmverspec
from packaging.version import InvalidVersion, Version

#: Forward-only promotion ladder (no branch theatre).
PROMOTION_ORDER: tuple[str, ...] = ("dev", "beta", "stable")

_CHANNEL_ASSIGN_RE = re.compile(
    r'^(release_channel\s*=\s*")(?P<value>[^"]*)("\s*)$',
    re.MULTILINE,
)


@dataclass(frozen=True)
class PromotionPlan:
    """Planned channel/tag change (dry-run friendly)."""

    from_channel: str
    to_channel: str
    version: str
    tag_name: str
    prerelease_github: bool
    notes: tuple[str, ...] = ()


def channel_rank(channel: str) -> int:
    """Return ladder index for ``channel`` (raises on unknown)."""
    ch = cdmverspec.normalize_release_channel(channel, default="")
    if ch not in PROMOTION_ORDER:
        raise ValueError(f"unknown channel: {channel!r}")
    return PROMOTION_ORDER.index(ch)


def can_promote(from_channel: str, to_channel: str, *, allow_skip: bool = False) -> bool:
    """True if ``from_channel`` → ``to_channel`` is a valid forward promotion."""
    try:
        src = channel_rank(from_channel)
        dst = channel_rank(to_channel)
    except ValueError:
        return False
    if dst <= src:
        return False
    if allow_skip:
        return True
    return dst == src + 1


def assert_can_promote(from_channel: str, to_channel: str, *, allow_skip: bool = False) -> None:
    """Raise ``ValueError`` when the promotion is not allowed."""
    if not can_promote(from_channel, to_channel, allow_skip=allow_skip):
        raise ValueError(
            f"illegal promotion {from_channel!r} → {to_channel!r} "
            f"(order={'→'.join(PROMOTION_ORDER)}; use --allow-skip for jumps)"
        )


def next_channel(channel: str) -> Optional[str]:
    """Return the next channel on the ladder, or ``None`` at ``stable``."""
    rank = channel_rank(channel)
    if rank >= len(PROMOTION_ORDER) - 1:
        return None
    return PROMOTION_ORDER[rank + 1]


def channel_from_pep440_version(version: str) -> str:
    """Infer channel from a PEP 440 version string.

    - final (no pre/dev) → ``stable``
    - ``.devN`` → ``dev``
    - other pre-releases (a/b/rc) → ``beta``
    """
    try:
        ver = Version(version)
    except InvalidVersion as exc:
        raise ValueError(f"invalid version: {version!r}") from exc
    if ver.dev is not None:
        return "dev"
    if ver.pre is not None:
        return "beta"
    return "stable"


def tag_to_version(tag_name: str) -> str:
    """Strip a leading ``v`` from a git tag name."""
    raw = (tag_name or "").strip()
    if raw.startswith("v") or raw.startswith("V"):
        return raw[1:]
    return raw


def suggest_tag(version: str, channel: str) -> str:
    """Suggest a git tag for ``version`` at ``channel``.

    If ``version`` already matches the channel's PEP 440 shape, return ``v`` +
    version. Otherwise append a minimal pre-release suffix for beta/dev.
    """
    ch = cdmverspec.normalize_release_channel(channel)
    try:
        ver = Version(version)
    except InvalidVersion as exc:
        raise ValueError(f"invalid version: {version!r}") from exc

    implied = channel_from_pep440_version(version)
    if implied == ch:
        return f"v{version}"

    base = ver.base_version
    if ch == "stable":
        return f"v{base}"
    if ch == "beta":
        return f"v{base}b1"
    return f"v{base}.dev1"


def github_prerelease_flag(channel: str) -> bool:
    """Whether a GitHub Release for ``channel`` should be marked prerelease."""
    return bool(cdmverspec.normalize_release_channel(channel) != "stable")


def plan_promotion(
    *,
    to_channel: str,
    from_channel: Optional[str] = None,
    version: Optional[str] = None,
    allow_skip: bool = False,
) -> PromotionPlan:
    """Build a promotion plan (does not write files)."""
    src = cdmverspec.normalize_release_channel(from_channel or cdmverspec.release_channel)
    dst = cdmverspec.normalize_release_channel(to_channel)
    assert_can_promote(src, dst, allow_skip=allow_skip)
    ver = version or cdmverspec.version
    tag = suggest_tag(ver, dst)
    notes = (
        "Solo-fork: promote via tag + cdmverspec.release_channel; no stable/develop branches.",
        f"After apply: commit cdmverspec, then `git tag -a {tag}` and push the tag.",
        "release.yml verifies tag vs version and channel vs PEP 440 shape.",
    )
    return PromotionPlan(
        from_channel=src,
        to_channel=dst,
        version=ver,
        tag_name=tag,
        prerelease_github=github_prerelease_flag(dst),
        notes=notes,
    )


def validate_tag_against_channel(tag_name: str, channel: str) -> None:
    """Fail closed when tag PEP 440 shape disagrees with ``channel``."""
    ver = tag_to_version(tag_name)
    implied = channel_from_pep440_version(ver)
    ch = cdmverspec.normalize_release_channel(channel)
    if implied != ch:
        raise ValueError(f"tag {tag_name!r} implies channel {implied!r}, but cdmverspec channel is {ch!r}")


def validate_tag_against_cdmverspec(
    tag_name: str,
    *,
    version: Optional[str] = None,
    channel: Optional[str] = None,
) -> None:
    """Validate tag matches baked ``version`` and channel shape."""
    ver = version or cdmverspec.version
    ch = channel or cdmverspec.release_channel
    tag_ver = tag_to_version(tag_name)
    if tag_ver != ver:
        raise ValueError(f"tag version {tag_ver!r} != cdmverspec.version {ver!r}")
    validate_tag_against_channel(tag_name, ch)


def read_cdmverspec_text(path: Path) -> str:
    """Read ``cdmverspec.py`` as text."""
    return path.read_text(encoding="utf-8")


def rewrite_release_channel(text: str, channel: str) -> str:
    """Return ``text`` with ``release_channel = "…"`` updated."""
    ch = cdmverspec.normalize_release_channel(channel)
    if ch not in cdmverspec.VALID_RELEASE_CHANNELS:
        raise ValueError(f"invalid channel: {channel!r}")
    if _CHANNEL_ASSIGN_RE.search(text) is None:
        raise ValueError("release_channel assignment not found in cdmverspec.py")
    return _CHANNEL_ASSIGN_RE.sub(rf"\1{ch}\3", text, count=1)


def apply_promotion_to_cdmverspec(path: Path, plan: PromotionPlan) -> None:
    """Write ``plan.to_channel`` into ``cdmverspec.py`` at ``path``."""
    original = read_cdmverspec_text(path)
    updated = rewrite_release_channel(original, plan.to_channel)
    if updated == original:
        return
    path.write_text(updated, encoding="utf-8")


def format_plan(plan: PromotionPlan) -> str:
    """Human-readable promotion plan for CLI / docs."""
    lines = [
        f"Promotion: {plan.from_channel} → {plan.to_channel}",
        f"Version:   {plan.version}",
        f"Tag:       {plan.tag_name}",
        f"GitHub prerelease flag: {plan.prerelease_github}",
        "Notes:",
    ]
    for note in plan.notes:
        lines.append(f"  - {note}")
    return "\n".join(lines)


def default_cdmverspec_path(repo_root: Optional[Path] = None) -> Path:
    """Return path to ``codimension/cdmverspec.py``."""
    root = repo_root if repo_root is not None else Path(__file__).resolve().parents[1]
    return root / "cdmverspec.py"


__all__ = [
    "PROMOTION_ORDER",
    "PromotionPlan",
    "apply_promotion_to_cdmverspec",
    "assert_can_promote",
    "can_promote",
    "channel_from_pep440_version",
    "channel_rank",
    "default_cdmverspec_path",
    "format_plan",
    "github_prerelease_flag",
    "next_channel",
    "plan_promotion",
    "read_cdmverspec_text",
    "rewrite_release_channel",
    "suggest_tag",
    "tag_to_version",
    "validate_tag_against_cdmverspec",
    "validate_tag_against_channel",
]
