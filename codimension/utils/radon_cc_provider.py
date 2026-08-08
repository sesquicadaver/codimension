# -*- coding: utf-8 -*-
#
# codimension - radon cyclomatic complexity MetricProvider (R134)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Radon CC adapter implementing ``core.metrics.MetricProvider`` (R134).

Wraps ``radon.complexity.cc_visit_ast`` / ``cc_rank`` without touching the
existing pyflakes / status-bar UI path in ``analysis.ierrors``.
"""

from __future__ import annotations

from _ast import PyCF_ONLY_AST
from typing import Optional

from core.metrics import MetricReport, MetricSample
from radon.complexity import cc_rank, cc_visit_ast, sorted_results


class RadonCCMetricProvider:
    """MetricProvider for radon cyclomatic complexity."""

    provider_id = "radon_cc"
    metric_id = "cyclomatic_complexity"

    def compute(self, source: str, *, path: Optional[str] = None) -> MetricReport:
        """Return CC samples for functions/methods/classes in ``source``."""
        text = source if source.endswith("\n") else source + "\n"
        try:
            tree = compile(text, path or "<string>", "exec", PyCF_ONLY_AST)
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
                error=f"CompileError: {exc}",
            )

        samples: list[MetricSample] = []
        for item in sorted_results(cc_visit_ast(tree)):
            complexity = float(item.complexity)
            kind = "method" if getattr(item, "is_method", False) else type(item).__name__.lower()
            classname = getattr(item, "classname", None)
            extras: dict[str, str] = {}
            if classname:
                extras["classname"] = str(classname)
            samples.append(
                MetricSample(
                    name=str(item.name),
                    value=complexity,
                    kind=kind,
                    rank=cc_rank(item.complexity),
                    line=getattr(item, "lineno", None),
                    endline=getattr(item, "endline", None),
                    path=path,
                    extras=extras,
                )
            )
        return MetricReport(
            provider_id=self.provider_id,
            metric_id=self.metric_id,
            samples=tuple(samples),
        )


def register_radon_cc(registry: object) -> RadonCCMetricProvider:
    """Create a RadonCC provider and register it on ``registry``."""
    provider = RadonCCMetricProvider()
    register = getattr(registry, "register", None)
    if register is None:
        raise TypeError("registry must provide register(provider)")
    register(provider)
    return provider


__all__ = ["RadonCCMetricProvider", "register_radon_cc"]
