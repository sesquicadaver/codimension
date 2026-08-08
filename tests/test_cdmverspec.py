# -*- coding: utf-8 -*-
"""R171: release channel metadata in cdmverspec."""

from __future__ import annotations

import cdmverspec


def test_version_and_default_channel() -> None:
    assert isinstance(cdmverspec.version, str) and cdmverspec.version
    assert cdmverspec.release_channel in cdmverspec.VALID_RELEASE_CHANNELS
    assert cdmverspec.release_channel == "stable"
    assert cdmverspec.VALID_RELEASE_CHANNELS == frozenset({"stable", "beta", "dev"})


def test_normalize_release_channel() -> None:
    assert cdmverspec.normalize_release_channel("BETA") == "beta"
    assert cdmverspec.normalize_release_channel("  Dev ") == "dev"
    assert cdmverspec.normalize_release_channel("nope") == "stable"
    assert cdmverspec.normalize_release_channel(None, default="beta") == "beta"


def test_env_override_for_channel() -> None:
    assert cdmverspec.get_release_channel(environ={}) == "stable"
    assert cdmverspec.get_release_channel(environ={cdmverspec.RELEASE_CHANNEL_ENV: "dev"}) == "dev"
    assert cdmverspec.get_release_channel(environ={cdmverspec.RELEASE_CHANNEL_ENV: "weird"}) == "stable"


def test_version_with_channel_display() -> None:
    text = cdmverspec.version_with_channel(environ={})
    assert text == f"{cdmverspec.version} (stable)"
    text_dev = cdmverspec.version_with_channel(environ={cdmverspec.RELEASE_CHANNEL_ENV: "dev"})
    assert text_dev == f"{cdmverspec.version} (dev)"
