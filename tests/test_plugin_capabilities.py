# -*- coding: utf-8 -*-
"""R150: plugin API / capability negotiation."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from plugins.capabilities import (
    HOST_CAPABILITIES,
    HOST_PLUGIN_API_VERSION,
    PluginCapabilitySpec,
    negotiate_plugin_capabilities,
)


def test_legacy_none_spec_accepted() -> None:
    result = negotiate_plugin_capabilities(None)
    assert result.ok


def test_compatible_required_capabilities() -> None:
    spec = PluginCapabilitySpec(
        min_api_version=1,
        required=frozenset({"wizard", "vcs"}),
    )
    result = negotiate_plugin_capabilities(spec)
    assert result.ok
    assert not result.missing


def test_missing_capability_rejected() -> None:
    spec = PluginCapabilitySpec(required=frozenset({"telepathy"}))
    result = negotiate_plugin_capabilities(spec)
    assert not result.ok
    assert "telepathy" in result.missing
    assert "missing required capabilities" in result.reason


def test_host_api_too_old_rejected() -> None:
    spec = PluginCapabilitySpec(min_api_version=HOST_PLUGIN_API_VERSION + 1)
    result = negotiate_plugin_capabilities(spec)
    assert not result.ok
    assert "older than plugin minimum" in result.reason


def test_host_api_too_new_rejected() -> None:
    spec = PluginCapabilitySpec(min_api_version=1, max_api_version=0)
    result = negotiate_plugin_capabilities(
        spec,
        host_api_version=1,
        host_capabilities=HOST_CAPABILITIES,
    )
    assert not result.ok
    assert "newer than plugin maximum" in result.reason


def _ensure_imp() -> None:
    """Install imp shim so yapsy can import on Python 3.12+."""
    try:
        from imp_compat import ensure_imp_compat
    except ImportError:
        from codimension.imp_compat import ensure_imp_compat  # type: ignore[no-redef]

    ensure_imp_compat()


def test_manager_constant_and_base_default() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PyQt5.QtWidgets")
    root = str(Path(__file__).resolve().parents[1] / "codimension")
    if root not in sys.path:
        sys.path.insert(0, root)
    _ensure_imp()
    from plugins.categories.cdmpluginbase import CDMPluginBase
    from plugins.manager.pluginmanager import CDMPluginManager

    assert CDMPluginBase.getCapabilityRequirements() is None
    assert CDMPluginManager.INCOMPATIBLE_CAPABILITIES == 8


def test_ruff_plugin_declares_compatible_spec() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PyQt5.QtWidgets")
    _ensure_imp()
    from cdmplugins.ruff import RuffPlugin

    spec = RuffPlugin.getCapabilityRequirements()
    assert spec is not None
    result = negotiate_plugin_capabilities(spec)
    assert result.ok, result.reason
