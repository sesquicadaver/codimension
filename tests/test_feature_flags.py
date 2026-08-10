# -*- coding: utf-8 -*-
"""R174: persistent experimental feature flags."""

from __future__ import annotations

from pathlib import Path

import pytest
from core.ai_ui import AiAction, is_ai_ui_enabled, list_ai_menu_entries, run_ai_action_for_source
from core.feature_flags import (
    FLAG_AI_UI,
    KNOWN_FLAGS,
    FeatureFlagsStore,
    default_feature_flags_path,
    is_feature_enabled,
    reset_feature_flags_store_for_tests,
    set_feature_enabled,
)

_SRC = "def target():\n    return 1\n"


def test_default_path() -> None:
    path = default_feature_flags_path(home="/tmp/cdm-home")
    assert path.endswith("feature_flags.json")
    assert ".codimension3" in path


def test_store_defaults_off_and_persists(tmp_path: Path) -> None:
    path = tmp_path / "feature_flags.json"
    store = FeatureFlagsStore(str(path))
    assert store.is_enabled(FLAG_AI_UI) is False
    assert FLAG_AI_UI in KNOWN_FLAGS

    store.set_enabled(FLAG_AI_UI, True)
    assert path.is_file()
    reloaded = FeatureFlagsStore(str(path))
    assert reloaded.is_enabled(FLAG_AI_UI) is True

    reloaded.set_enabled(FLAG_AI_UI, False)
    assert FeatureFlagsStore(str(path)).is_enabled(FLAG_AI_UI) is False


def test_unknown_flag_rejected(tmp_path: Path) -> None:
    store = FeatureFlagsStore(str(tmp_path / "f.json"))
    with pytest.raises(ValueError, match="unknown"):
        store.set_enabled("not_a_flag", True)


def test_env_override_wins_over_store(tmp_path: Path) -> None:
    store = FeatureFlagsStore(str(tmp_path / "f.json"))
    store.set_enabled(FLAG_AI_UI, True)
    assert is_feature_enabled(FLAG_AI_UI, store=store, environ={"CDM_AI_UI": "0"}) is False
    assert is_feature_enabled(FLAG_AI_UI, store=store, environ={"CDM_AI_UI": "1"}) is True


def test_explicit_environ_without_key_ignores_disk() -> None:
    """Unit isolation: environ={} must not read the process-wide disk store."""
    reset_feature_flags_store_for_tests()
    assert is_feature_enabled(FLAG_AI_UI, environ={}) is False
    assert is_ai_ui_enabled(environ={}) is False


def test_ai_ui_gated_by_persistent_flag(tmp_path: Path) -> None:
    store = FeatureFlagsStore(str(tmp_path / "f.json"))
    assert list_ai_menu_entries(environ={}, store=store) == ()
    set_feature_enabled(FLAG_AI_UI, True, store=store)
    entries = list_ai_menu_entries(environ={}, store=store)
    assert [a for a, _ in entries] == [AiAction.EXPLAIN, AiAction.SUGGEST]
    result = run_ai_action_for_source(
        AiAction.EXPLAIN,
        _SRC,
        "target",
        environ={},
        store=store,
        home=str(tmp_path),
    )
    assert "target" in result.text
