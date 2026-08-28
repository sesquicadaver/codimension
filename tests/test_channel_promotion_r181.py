# -*- coding: utf-8 -*-
"""R181: channel promotion ladder + tag validation (no network)."""

from __future__ import annotations

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


def test_promotion_ladder_one_step():
    from utils.channel_promotion import can_promote, next_channel, plan_promotion

    assert next_channel("dev") == "beta"
    assert next_channel("beta") == "stable"
    assert next_channel("stable") is None
    assert can_promote("dev", "beta")
    assert can_promote("beta", "stable")
    assert not can_promote("dev", "stable")
    assert can_promote("dev", "stable", allow_skip=True)
    assert not can_promote("stable", "beta")

    plan = plan_promotion(to_channel="beta", from_channel="dev", version="4.12.0")
    assert plan.tag_name == "v4.12.0b1"
    assert plan.prerelease_github is True


def test_suggest_tag_respects_existing_shape():
    from utils.channel_promotion import suggest_tag

    assert suggest_tag("4.12.0", "stable") == "v4.12.0"
    assert suggest_tag("4.12.0b2", "beta") == "v4.12.0b2"
    assert suggest_tag("4.12.0.dev3", "dev") == "v4.12.0.dev3"
    assert suggest_tag("4.12.0", "dev") == "v4.12.0.dev1"


def test_channel_from_pep440():
    from utils.channel_promotion import channel_from_pep440_version

    assert channel_from_pep440_version("4.12.0") == "stable"
    assert channel_from_pep440_version("4.12.0b1") == "beta"
    assert channel_from_pep440_version("4.12.0rc1") == "beta"
    assert channel_from_pep440_version("4.12.0.dev1") == "dev"


def test_validate_tag_against_cdmverspec_ok(monkeypatch):
    import cdmverspec
    from utils.channel_promotion import validate_tag_against_cdmverspec

    monkeypatch.setattr(cdmverspec, "version", "4.12.0")
    monkeypatch.setattr(cdmverspec, "release_channel", "stable")
    validate_tag_against_cdmverspec("v4.12.0")


def test_validate_tag_mismatch_channel(monkeypatch):
    import cdmverspec
    from utils.channel_promotion import validate_tag_against_cdmverspec

    monkeypatch.setattr(cdmverspec, "version", "4.12.0b1")
    monkeypatch.setattr(cdmverspec, "release_channel", "stable")
    with pytest.raises(ValueError, match="implies channel"):
        validate_tag_against_cdmverspec("v4.12.0b1")


def test_rewrite_release_channel(tmp_path):
    from utils.channel_promotion import (
        PromotionPlan,
        apply_promotion_to_cdmverspec,
        rewrite_release_channel,
    )

    text = 'version = "4.11.0"\nrelease_channel = "dev"\n'
    assert 'release_channel = "beta"' in rewrite_release_channel(text, "beta")
    path = tmp_path / "cdmverspec.py"
    path.write_text(text, encoding="utf-8")
    plan = PromotionPlan(
        from_channel="dev",
        to_channel="beta",
        version="4.11.0",
        tag_name="v4.11.0b1",
        prerelease_github=True,
    )
    apply_promotion_to_cdmverspec(path, plan)
    assert 'release_channel = "beta"' in path.read_text(encoding="utf-8")


def test_cli_validate_and_dry_run():
    import subprocess

    script = Path(__file__).resolve().parents[1] / "scripts" / "promote_release_channel.py"
    completed = subprocess.run(
        [sys.executable, str(script), "--from-channel", "dev", "--to", "beta"],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(script.parents[1]),
    )
    assert completed.returncode == 0, completed.stderr
    assert "dev → beta" in completed.stdout
    assert "Dry-run" in completed.stdout

    completed2 = subprocess.run(
        [sys.executable, str(script), "--validate-tag", "v4.11.0"],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(script.parents[1]),
    )
    assert completed2.returncode == 0, completed2.stderr
    assert "OK:" in completed2.stdout
