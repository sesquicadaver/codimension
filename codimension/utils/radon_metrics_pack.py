# -*- coding: utf-8 -*-
#
# codimension - advanced radon metrics pack (R136)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Advanced radon metrics behind ``MetricProvider`` (R136).

Documented subset beyond cyclomatic complexity (R134):

* **Maintainability index** — ``radon.metrics.mi_visit`` / ``mi_rank``
* **Halstead** — ``h_visit``; primary sample value is *volume*
* **Raw size** — ``radon.raw.analyze``; primary sample value is *LOC*

UI viewers stay on the existing CC path until a later wiring task.
"""

from __future__ import annotations

from typing import Optional

from core.metrics import MetricReport, MetricSample
from radon.metrics import h_visit, mi_rank, mi_visit
from radon.raw import analyze as raw_analyze


def _normalize_source(source: str) -> str:
    """Ensure a trailing newline for radon parsers."""
    return source if source.endswith("\n") else source + "\n"


class RadonMIMetricProvider:
    """MetricProvider for radon maintainability index (module-level)."""

    provider_id = "radon_mi"
    metric_id = "maintainability_index"

    def compute(self, source: str, *, path: Optional[str] = None) -> MetricReport:
        """Return a single module MI sample."""
        text = _normalize_source(source)
        try:
            score = float(mi_visit(text, multi=True))
        except SyntaxError as exc:
            return MetricReport(
                provider_id=self.provider_id,
                metric_id=self.metric_id,
                error=f"SyntaxError: {exc.msg}",
            )
        except (ValueError, TypeError) as exc:
            return MetricReport(
                provider_id=self.provider_id,
                metric_id=self.metric_id,
                error=f"MetricError: {exc}",
            )
        return MetricReport(
            provider_id=self.provider_id,
            metric_id=self.metric_id,
            samples=(
                MetricSample(
                    name="<module>",
                    value=score,
                    kind="module",
                    rank=mi_rank(score),
                    path=path,
                ),
            ),
        )


class RadonHalsteadMetricProvider:
    """MetricProvider for Halstead volume (module + per-function)."""

    provider_id = "radon_halstead"
    metric_id = "halstead_volume"

    def compute(self, source: str, *, path: Optional[str] = None) -> MetricReport:
        """Return Halstead volume samples; other fields live in ``extras``."""
        text = _normalize_source(source)
        try:
            result = h_visit(text)
        except SyntaxError as exc:
            return MetricReport(
                provider_id=self.provider_id,
                metric_id=self.metric_id,
                error=f"SyntaxError: {exc.msg}",
            )
        except (ValueError, TypeError) as exc:
            return MetricReport(
                provider_id=self.provider_id,
                metric_id=self.metric_id,
                error=f"MetricError: {exc}",
            )

        samples: list[MetricSample] = [
            MetricSample(
                name="<module>",
                value=float(result.total.volume),
                kind="module",
                path=path,
                extras=_halstead_extras(result.total),
            )
        ]
        for name, report in result.functions:
            samples.append(
                MetricSample(
                    name=str(name),
                    value=float(report.volume),
                    kind="function",
                    path=path,
                    extras=_halstead_extras(report),
                )
            )
        return MetricReport(
            provider_id=self.provider_id,
            metric_id=self.metric_id,
            samples=tuple(samples),
        )


class RadonRawMetricProvider:
    """MetricProvider for radon raw size metrics (LOC primary)."""

    provider_id = "radon_raw"
    metric_id = "raw_loc"

    def compute(self, source: str, *, path: Optional[str] = None) -> MetricReport:
        """Return a module LOC sample with related raw fields in extras."""
        text = _normalize_source(source)
        try:
            module = raw_analyze(text)
        except (SyntaxError, ValueError, TypeError) as exc:
            msg = getattr(exc, "msg", None) or str(exc)
            kind = type(exc).__name__
            return MetricReport(
                provider_id=self.provider_id,
                metric_id=self.metric_id,
                error=f"{kind}: {msg}",
            )
        extras = {
            "lloc": str(module.lloc),
            "sloc": str(module.sloc),
            "comments": str(module.comments),
            "multi": str(module.multi),
            "blank": str(module.blank),
            "single_comments": str(module.single_comments),
        }
        return MetricReport(
            provider_id=self.provider_id,
            metric_id=self.metric_id,
            samples=(
                MetricSample(
                    name="<module>",
                    value=float(module.loc),
                    kind="module",
                    path=path,
                    extras=extras,
                ),
            ),
        )


def _halstead_extras(report: object) -> dict[str, str]:
    """Serialize secondary Halstead fields for MetricSample.extras."""
    fields = (
        "h1",
        "h2",
        "N1",
        "N2",
        "vocabulary",
        "length",
        "difficulty",
        "effort",
        "time",
        "bugs",
    )
    extras: dict[str, str] = {}
    for key in fields:
        if hasattr(report, key):
            extras[key] = str(getattr(report, key))
    return extras


def register_radon_advanced_pack(registry: object) -> tuple[object, ...]:
    """Register MI, Halstead, and raw providers on ``registry``."""
    register = getattr(registry, "register", None)
    if register is None:
        raise TypeError("registry must provide register(provider)")
    providers = (
        RadonMIMetricProvider(),
        RadonHalsteadMetricProvider(),
        RadonRawMetricProvider(),
    )
    for provider in providers:
        register(provider)
    return providers


__all__ = [
    "RadonHalsteadMetricProvider",
    "RadonMIMetricProvider",
    "RadonRawMetricProvider",
    "register_radon_advanced_pack",
]
