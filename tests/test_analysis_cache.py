# -*- coding: utf-8 -*-
"""R113: analysis cache registry + invalidate on env / file / project."""

from __future__ import annotations

import os
from pathlib import Path

import parsers  # noqa: E402,F401
import pytest
from utils.analysis_cache import (
    VALID_INVALIDATE_SCOPES,
    AnalysisCacheRegistry,
    CallableAnalysisCache,
    ensure_default_analysis_caches,
    get_analysis_cache_registry,
    get_brief_module_info_cache,
    get_control_flow_info_cache,
    invalidate_analysis_caches,
    reset_analysis_cache_registry_for_tests,
)
from utils.briefmodinfocache import BriefModuleInfoCache


@pytest.fixture(autouse=True)
def _reset_registry():
    """Isolate registry state between tests."""
    reset_analysis_cache_registry_for_tests()
    yield
    reset_analysis_cache_registry_for_tests()


@pytest.fixture
def sample_py(tmp_path: Path) -> Path:
    """A tiny Python file for brief/flow cache population."""
    path = tmp_path / "mod.py"
    path.write_text("def hello():\n    return 1\n", encoding="utf-8")
    return path


def test_invalidate_scopes_are_documented() -> None:
    """API scopes match ROADMAP contract."""
    assert VALID_INVALIDATE_SCOPES == {"project", "file", "env"}


def test_registry_rejects_unknown_scope() -> None:
    """Unknown scopes raise ValueError."""
    reg = AnalysisCacheRegistry()
    with pytest.raises(ValueError, match="unknown invalidate scope"):
        reg.invalidate("nope")  # type: ignore[arg-type]


def test_file_invalidate_requires_path() -> None:
    """file scope without path is an error."""
    reg = AnalysisCacheRegistry()
    with pytest.raises(ValueError, match="requires path"):
        reg.invalidate("file")


def test_callable_adapter_file_and_all() -> None:
    """Adapter forwards file/all invalidation."""
    removed: list[str] = []
    cleared: list[int] = []

    def remove(path: str) -> None:
        removed.append(path)

    def clear() -> None:
        cleared.append(1)

    reg = AnalysisCacheRegistry()
    reg.register(CallableAnalysisCache("stub", remove, clear))
    assert reg.names() == ("stub",)

    n = reg.invalidate("file", path="/tmp/x.py")
    assert n == 1
    assert removed and os.path.isabs(removed[0])

    n = reg.invalidate("env")
    assert n == 1
    assert cleared == [1]

    n = reg.invalidate("project")
    assert n == 1
    assert cleared == [1, 1]


def test_default_caches_register_brief_and_flow(sample_py: Path) -> None:
    """ensure_default_analysis_caches registers brief + flow and shares instances."""
    reg = ensure_default_analysis_caches()
    assert set(reg.names()) == {"brief", "flow"}
    brief = get_brief_module_info_cache()
    flow = get_control_flow_info_cache()
    assert isinstance(brief, BriefModuleInfoCache)

    brief.get(str(sample_py))
    flow.get(str(sample_py))
    assert str(sample_py.resolve()) in brief or sample_py in brief
    assert sample_py in flow
    assert brief.size() >= 1
    assert flow.size() >= 1


def test_env_invalidate_purges_stale_brief_and_flow(sample_py: Path) -> None:
    """Interpreter/env refresh clears brief+flow even when mtime is unchanged."""
    ensure_default_analysis_caches()
    brief = get_brief_module_info_cache()
    flow = get_control_flow_info_cache()
    brief.get(str(sample_py))
    flow.get(str(sample_py))
    assert brief.size() == 1
    assert flow.size() == 1

    notified = invalidate_analysis_caches("env")
    assert notified == 2
    assert brief.size() == 0
    assert flow.size() == 0
    assert sample_py not in brief
    assert sample_py not in flow


def test_file_invalidate_drops_one_path(tmp_path: Path) -> None:
    """file scope removes only the named path."""
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("x = 1\n", encoding="utf-8")
    b.write_text("y = 2\n", encoding="utf-8")
    ensure_default_analysis_caches()
    brief = get_brief_module_info_cache()
    brief.get(str(a))
    brief.get(str(b))
    assert brief.size() == 2

    invalidate_analysis_caches("file", path=str(a))
    assert a not in brief
    assert b in brief
    assert brief.size() == 1


def test_request_analysis_environment_refresh_clears_caches(sample_py: Path, tmp_path: Path) -> None:
    """venvbootstrap env refresh purges registered analysis caches (R113)."""
    from unittest.mock import MagicMock

    from utils import venvbootstrap as vb

    ensure_default_analysis_caches()
    brief = get_brief_module_info_cache()
    brief.get(str(sample_py))
    assert brief.size() == 1

    proj = MagicMock()
    proj.isLoaded.return_value = True
    proj.getProjectDir.return_value = str(tmp_path) + os.sep
    proj.props = {"pythoninterpreter": "", "uuid": "r113"}
    proj.refreshAnalysisEnvironment = MagicMock()

    vb.requestAnalysisEnvironmentRefresh(proj)
    proj.refreshAnalysisEnvironment.assert_called_once()
    assert brief.size() == 0


def test_registry_singleton_reset() -> None:
    """reset drops singleton so the next get rebuilds a fresh registry."""
    a = get_analysis_cache_registry()
    a.register(CallableAnalysisCache("tmp", lambda _p: None, lambda: None))
    reset_analysis_cache_registry_for_tests()
    b = get_analysis_cache_registry()
    assert a is not b
    assert b.names() == ()
