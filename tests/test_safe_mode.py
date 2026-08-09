# -*- coding: utf-8 -*-
"""R175: safe-mode startup (plugins / overlays off)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import parsers  # noqa: E402,F401
import pytest

_CODIM = Path(__file__).resolve().parents[1] / "codimension"


@pytest.fixture(autouse=True)
def _purge_and_reset():
    import importlib

    from core.safe_mode import reset_safe_mode_for_tests

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
    reset_safe_mode_for_tests()
    yield
    reset_safe_mode_for_tests()


def test_safe_mode_off_by_default() -> None:
    from core.safe_mode import is_safe_mode_enabled, safe_mode_reason

    assert is_safe_mode_enabled(environ={}) is False
    assert is_safe_mode_enabled(environ={"CDM_SAFE_MODE": "0"}) is False
    assert safe_mode_reason(environ={}) is None


def test_safe_mode_env_truthy() -> None:
    from core.safe_mode import SAFE_MODE_ENV, is_safe_mode_enabled, safe_mode_reason

    for value in ("1", "true", "YES", "On"):
        assert is_safe_mode_enabled(environ={SAFE_MODE_ENV: value}) is True
    assert "CDM_SAFE_MODE" in (safe_mode_reason(environ={SAFE_MODE_ENV: "1"}) or "")


def test_cli_latch_enables_safe_mode() -> None:
    from core.safe_mode import activate_safe_mode_from_cli, is_safe_mode_enabled, safe_mode_reason

    assert is_safe_mode_enabled(environ={}) is False
    activate_safe_mode_from_cli()
    assert is_safe_mode_enabled(environ={}) is True
    assert safe_mode_reason(environ={}) == "CLI --safe-mode"


def test_overlays_disabled_in_safe_mode() -> None:
    from core.safe_mode import activate_safe_mode_from_cli
    from utils.dependency_overlay import empty_deps_heat_badge, ensure_dependency_overlay
    from utils.deployment_overlay import empty_deployment_badge, ensure_deployment_overlay
    from utils.environment_overlay import ensure_environment_overlay
    from utils.overlay_host import OverlayHost, notify_flow_overlays

    activate_safe_mode_from_cli()
    env = ensure_environment_overlay()
    deps = ensure_dependency_overlay()
    deploy = ensure_deployment_overlay()
    assert env.refresh().source_badge == ""
    assert deps.refresh() == empty_deps_heat_badge()
    assert deploy.refresh() == empty_deployment_badge()

    host = OverlayHost("flow-test")
    called: list[str] = []

    class Probe:
        layer_id = "probe"

        def on_update(self, context) -> None:
            called.append(context.reason)

    host.register(Probe())
    # Process-wide notify must be a no-op in safe mode.
    notify_flow_overlays("redraw")
    assert called == []


def test_plugin_manager_load_skipped() -> None:
    """``load`` returns before collect when safe mode is on (no full manager init)."""
    from types import SimpleNamespace

    from core.safe_mode import activate_safe_mode_from_cli
    from imp_compat import ensure_imp_compat

    ensure_imp_compat()
    from plugins.manager.pluginmanager import CDMPluginManager

    activate_safe_mode_from_cli()
    # Unbound call: guard must return before any ``self`` use / collect.
    CDMPluginManager.load(SimpleNamespace())
