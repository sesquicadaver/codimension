# -*- coding: utf-8 -*-
"""R134: MetricProvider protocol, registry, and radon CC adapter."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
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


@dataclass
class FakeMetricProvider:
    """Recording stand-in used to prove the protocol / registry surface."""

    provider_id: str = "fake"
    metric_id: str = "fake_metric"
    calls: list[tuple[str, str | None]] = field(default_factory=list)
    value: float = 1.0

    def compute(self, source: str, *, path: str | None = None):
        from core.metrics import MetricReport, MetricSample

        self.calls.append((source, path))
        return MetricReport(
            provider_id=self.provider_id,
            metric_id=self.metric_id,
            samples=(MetricSample(name="unit", value=self.value, path=path),),
        )


def test_fake_provider_satisfies_protocol_and_registry() -> None:
    from core.metrics import MetricProvider, MetricProviderRegistry, assert_metric_provider

    provider = FakeMetricProvider()
    assert isinstance(provider, MetricProvider)
    assert assert_metric_provider(provider) is provider

    registry = MetricProviderRegistry()
    registry.register(provider)
    assert registry.has("fake")
    assert registry.provider_ids() == ("fake",)
    report = registry.compute("fake", "pass\n", path="x.py")
    assert report.metric_id == "fake_metric"
    assert report.samples[0].value == 1.0
    assert provider.calls == [("pass\n", "x.py")]


def test_assert_metric_provider_rejects_incomplete() -> None:
    from core.metrics import assert_metric_provider

    class _NotAProvider:
        provider_id = "x"

    with pytest.raises(TypeError, match="MetricProvider"):
        assert_metric_provider(_NotAProvider())


def test_radon_cc_adapter_scores_functions() -> None:
    from core.metrics import MetricProvider, MetricProviderRegistry
    from utils.radon_cc_provider import RadonCCMetricProvider, register_radon_cc

    provider = RadonCCMetricProvider()
    assert isinstance(provider, MetricProvider)

    source = "def simple():\n    return 1\n\ndef branched(x):\n    if x:\n        return 1\n    return 0\n"
    report = provider.compute(source, path="sample.py")
    assert report.error is None
    assert report.provider_id == "radon_cc"
    assert report.metric_id == "cyclomatic_complexity"
    by_name = {s.name: s for s in report.samples}
    assert "simple" in by_name and "branched" in by_name
    assert by_name["branched"].value > by_name["simple"].value
    assert by_name["branched"].rank is not None
    assert by_name["branched"].path == "sample.py"

    registry = MetricProviderRegistry()
    register_radon_cc(registry)
    via_reg = registry.compute("radon_cc", source)
    assert {s.name for s in via_reg.samples} == {"simple", "branched"}


def test_radon_cc_syntax_error_report() -> None:
    from utils.radon_cc_provider import RadonCCMetricProvider

    report = RadonCCMetricProvider().compute("def broken(\n")
    assert report.samples == ()
    assert report.error is not None
    assert "SyntaxError" in report.error


def test_core_metrics_import_without_qt() -> None:
    root = Path(__file__).resolve().parents[1]
    code = (
        "import sys\n"
        f"sys.path.insert(0, {str(root / 'codimension')!r})\n"
        f"sys.path.insert(0, {str(root)!r})\n"
        "assert 'PyQt5' not in sys.modules\n"
        "from core.metrics import MetricProvider, MetricProviderRegistry\n"
        "assert 'PyQt5' not in sys.modules\n"
        "print('ok')\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)
    assert "ok" in proc.stdout
