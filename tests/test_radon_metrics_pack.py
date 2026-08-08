# -*- coding: utf-8 -*-
"""R136: advanced radon metrics pack behind MetricProvider."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import parsers  # noqa: E402,F401
import pytest

_CODIM = Path(__file__).resolve().parents[1] / "codimension"

# Fixture: branched function + method — MI/Halstead/raw must all produce samples.
_FIXTURE = '''\
"""sample module for advanced metrics."""

def simple():
    return 1

def branched(x):
    if x:
        return x + 1
    elif x is None:
        return -1
    return 0

class Worker:
    def run(self, a, b):
        return a if a else b
'''


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


def test_mi_and_halstead_beyond_cc() -> None:
    """At least two metrics beyond CC: maintainability + Halstead volume."""
    from core.metrics import MetricProvider, MetricProviderRegistry
    from utils.radon_metrics_pack import (
        RadonHalsteadMetricProvider,
        RadonMIMetricProvider,
        register_radon_advanced_pack,
    )

    mi = RadonMIMetricProvider()
    hs = RadonHalsteadMetricProvider()
    assert isinstance(mi, MetricProvider)
    assert isinstance(hs, MetricProvider)

    mi_report = mi.compute(_FIXTURE, path="fixture.py")
    assert mi_report.error is None
    assert mi_report.metric_id == "maintainability_index"
    assert len(mi_report.samples) == 1
    assert mi_report.samples[0].name == "<module>"
    assert mi_report.samples[0].value > 0
    assert mi_report.samples[0].rank in {"A", "B", "C"}

    hs_report = hs.compute(_FIXTURE, path="fixture.py")
    assert hs_report.error is None
    assert hs_report.metric_id == "halstead_volume"
    names = {s.name for s in hs_report.samples}
    assert "<module>" in names
    assert "branched" in names or "simple" in names
    module = next(s for s in hs_report.samples if s.name == "<module>")
    assert module.value >= 0
    assert "difficulty" in module.extras

    registry = MetricProviderRegistry()
    register_radon_advanced_pack(registry)
    assert registry.has("radon_mi")
    assert registry.has("radon_halstead")
    assert registry.has("radon_raw")
    assert {p.metric_id for p in registry.list_providers()} >= {
        "maintainability_index",
        "halstead_volume",
        "raw_loc",
    }


def test_raw_loc_provider() -> None:
    from utils.radon_metrics_pack import RadonRawMetricProvider

    report = RadonRawMetricProvider().compute(_FIXTURE)
    assert report.error is None
    sample = report.samples[0]
    assert sample.value > 0
    assert float(sample.value) >= float(sample.extras["sloc"])
    assert "lloc" in sample.extras


def test_mi_syntax_error() -> None:
    from utils.radon_metrics_pack import RadonMIMetricProvider

    report = RadonMIMetricProvider().compute("def broken(\n")
    assert report.samples == ()
    assert report.error is not None
    assert "SyntaxError" in report.error
