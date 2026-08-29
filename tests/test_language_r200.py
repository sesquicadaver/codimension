# -*- coding: utf-8 -*-
"""R200: LanguageServiceRegistry + feature-gated manager + additive SymbolRecord."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.language_services import LanguageServiceManager, is_language_services_enabled
from core.feature_flags import (
    FLAG_LANGUAGE_SERVICES,
    FeatureFlagsStore,
    is_feature_enabled,
)
from core.language import (
    PYTHON_HEADLESS_CAPABILITIES,
    LanguageCapability,
    LanguageDescriptor,
    LanguageService,
    LanguageServiceRegistry,
    make_python_language_service,
)
from core.symbol_index import (
    GenericSymbolKind,
    SymbolKind,
    build_symbol,
    generic_kind_for_symbol_kind,
)


def test_language_descriptor_rejects_empty_id() -> None:
    with pytest.raises(ValueError, match="language_id"):
        LanguageDescriptor(language_id="  ", extensions=frozenset({".py"}))


def test_registry_register_get_list() -> None:
    registry = LanguageServiceRegistry()
    service = make_python_language_service()
    registry.register(service)
    assert registry.has("python.headless")
    assert registry.get("python.headless") is service
    assert registry.service_ids() == ("python.headless",)
    assert registry.list_services() == (service,)
    assert registry.get_by_language_id("python") == (service,)
    assert service.has_capability(LanguageCapability.OUTLINE)
    assert LanguageCapability.DIAGNOSTICS not in service.capabilities
    assert service.capabilities == PYTHON_HEADLESS_CAPABILITIES


def test_registry_rejects_non_service() -> None:
    registry = LanguageServiceRegistry()
    with pytest.raises(TypeError):
        registry.register(object())  # type: ignore[arg-type]


def test_manager_noop_when_flag_off(tmp_path: Path) -> None:
    store = FeatureFlagsStore(str(tmp_path / "flags.json"))
    assert is_language_services_enabled(store=store, environ={}) is False
    mgr = LanguageServiceManager()
    assert mgr.ensure_defaults(store=store, environ={}) is False
    assert mgr.registry.list_services() == ()


def test_manager_registers_python_when_flag_on(tmp_path: Path) -> None:
    store = FeatureFlagsStore(str(tmp_path / "flags.json"))
    store.set_enabled(FLAG_LANGUAGE_SERVICES, True)
    assert is_feature_enabled(FLAG_LANGUAGE_SERVICES, store=store, environ={}) is True
    mgr = LanguageServiceManager()
    assert mgr.ensure_defaults(store=store, environ={}) is True
    assert mgr.registry.has("python.headless")
    # Idempotent
    assert mgr.ensure_defaults(store=store, environ={}) is True
    assert len(mgr.registry.list_services()) == 1
    mgr.shutdown()
    assert mgr.registry.list_services() == ()


def test_env_override_enables_language_services(tmp_path: Path) -> None:
    store = FeatureFlagsStore(str(tmp_path / "flags.json"))
    mgr = LanguageServiceManager()
    assert mgr.ensure_defaults(store=store, environ={"CDM_LANGUAGE_SERVICES": "1"}) is True
    assert mgr.registry.has("python.headless")


def test_symbol_record_additive_defaults() -> None:
    rec = build_symbol("foo", SymbolKind.FUNCTION, "a.py", 0, 3)
    assert rec.language_id == "python"
    assert rec.generic_kind is GenericSymbolKind.FUNCTION
    assert rec.provider_id == "python.brief"
    assert rec.native_kind == "python.function"
    assert rec.symbol_key == "python:a.py:foo:function"
    assert generic_kind_for_symbol_kind(SymbolKind.CLASS) is GenericSymbolKind.TYPE
    assert generic_kind_for_symbol_kind(SymbolKind.ATTRIBUTE) is GenericSymbolKind.FIELD


def test_language_service_custom_capabilities() -> None:
    svc = LanguageService(
        descriptor=LanguageDescriptor("rust", frozenset({".rs"}), ("Cargo.toml",)),
        capabilities=frozenset({LanguageCapability.DIAGNOSTICS, LanguageCapability.HOVER}),
    )
    assert svc.service_id == "rust"
    assert svc.has_capability(LanguageCapability.HOVER)
