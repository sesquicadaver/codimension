# -*- coding: utf-8 -*-
"""R152: AI UI actions behind CDM_AI_UI feature flag."""

from __future__ import annotations

from pathlib import Path

import pytest
from core.ai_config import PROVIDER_OPENAI, AiConfig, save_ai_config
from core.ai_http import AiBackendConfigError
from core.ai_ui import (
    AI_UI_ENV,
    AiAction,
    AiUiDisabledError,
    MockAiBackend,
    OfflineSummaryBackend,
    ai_ui_env_override_active,
    describe_ai_ui_settings,
    enable_ai_ui_for_tests,
    is_ai_ui_enabled,
    list_ai_menu_entries,
    resolve_default_backend,
    run_ai_action_for_source,
    set_ai_ui_enabled,
)
from core.feature_flags import FLAG_AI_UI, FeatureFlagsStore

_SRC = "def target(x):\n    if x:\n        return 1\n    return 2\n"


def test_flag_off_by_default() -> None:
    assert is_ai_ui_enabled(environ={}) is False
    assert is_ai_ui_enabled(environ={AI_UI_ENV: "0"}) is False
    assert list_ai_menu_entries(environ={}) == ()


def test_flag_truthy_values() -> None:
    for value in ("1", "true", "YES", "On"):
        assert is_ai_ui_enabled(environ={AI_UI_ENV: value}) is True
    entries = list_ai_menu_entries(environ={AI_UI_ENV: "1"})
    assert [a for a, _ in entries] == [AiAction.EXPLAIN, AiAction.SUGGEST]


def test_run_disabled_raises() -> None:
    with pytest.raises(AiUiDisabledError):
        run_ai_action_for_source(AiAction.EXPLAIN, _SRC, "target", environ={})


def test_explain_and_suggest_with_mock_backend() -> None:
    env: dict[str, str] = {}
    enable_ai_ui_for_tests(env)
    backend = MockAiBackend(prefix="smoke")
    explained = run_ai_action_for_source(AiAction.EXPLAIN, _SRC, "target", file="m.py", backend=backend, environ=env)
    suggested = run_ai_action_for_source(AiAction.SUGGEST, _SRC, "target", file="m.py", backend=backend, environ=env)
    assert explained.text == "smoke:explain:target"
    assert suggested.text == "smoke:suggest:target"
    assert explained.backend_name == "mock"


def test_offline_summary_backend_smoke() -> None:
    env = {AI_UI_ENV: "1"}
    result = run_ai_action_for_source(
        AiAction.EXPLAIN,
        _SRC,
        "target",
        file="m.py",
        backend=OfflineSummaryBackend(),
        environ=env,
    )
    assert "target" in result.text
    assert "CFG slice" in result.text
    suggest = run_ai_action_for_source(
        AiAction.SUGGEST,
        _SRC,
        "target",
        file="m.py",
        backend=OfflineSummaryBackend(),
        environ=env,
    )
    assert "Suggestions for target" in suggest.text


def test_set_ai_ui_enabled_and_describe(tmp_path: Path) -> None:
    store = FeatureFlagsStore(str(tmp_path / "feature_flags.json"))
    assert ai_ui_env_override_active(environ={}) is False
    set_ai_ui_enabled(True, store=store)
    assert store.is_enabled(FLAG_AI_UI) is True
    snap = describe_ai_ui_settings(environ={}, store=store)
    assert snap["enabled"] is True
    assert snap["store_enabled"] is True
    assert snap["env_override_active"] is False
    assert AI_UI_ENV in str(snap["env_key"])
    assert "offline" in str(snap["backend_label"]).lower()
    set_ai_ui_enabled(False, store=store)
    assert describe_ai_ui_settings(environ={}, store=store)["enabled"] is False


def test_env_override_active() -> None:
    assert ai_ui_env_override_active(environ={AI_UI_ENV: "1"}) is True
    assert ai_ui_env_override_active(environ={AI_UI_ENV: ""}) is False
    assert ai_ui_env_override_active(environ={}) is False


def test_resolve_default_backend_offline(tmp_path: Path) -> None:
    backend = resolve_default_backend(home=str(tmp_path))
    assert isinstance(backend, OfflineSummaryBackend)
    assert backend.name == "offline-summary"


def test_resolve_default_backend_openai_needs_key(tmp_path: Path) -> None:
    save_ai_config(
        AiConfig(provider=PROVIDER_OPENAI, model="gpt-4o-mini"),
        home=str(tmp_path),
    )
    with pytest.raises(AiBackendConfigError):
        resolve_default_backend(home=str(tmp_path))


def test_run_uses_offline_when_no_config(tmp_path: Path) -> None:
    env = {AI_UI_ENV: "1"}
    result = run_ai_action_for_source(
        AiAction.EXPLAIN,
        _SRC,
        "target",
        file="m.py",
        environ=env,
        home=str(tmp_path),
    )
    assert result.backend_name == "offline-summary"
    assert "target" in result.text


def test_describe_includes_provider(tmp_path: Path) -> None:
    store = FeatureFlagsStore(str(tmp_path / "feature_flags.json"))
    snap = describe_ai_ui_settings(environ={}, store=store, home=str(tmp_path))
    assert snap["provider"] == "offline"
    assert snap["api_key_configured"] is False
