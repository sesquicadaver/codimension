# -*- coding: utf-8 -*-
#
# codimension - headless MetricProvider contract (R134)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""MetricProvider protocol and registry (R134).

Qt-free contract for pluggable code metrics. Concrete adapters (e.g. radon
cyclomatic complexity) live outside ``core`` so the protocol stays free of
third-party metric engines. Existing UI viewers may keep calling radon
directly until a later wiring task.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping, Optional, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class MetricSample:
    """One measured entity (function, method, class, module, …)."""

    name: str
    value: float
    kind: str = "entity"
    rank: Optional[str] = None
    line: Optional[int] = None
    endline: Optional[int] = None
    path: Optional[str] = None
    extras: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Freeze ``extras`` as a mapping proxy."""
        extras = dict(self.extras) if self.extras else {}
        object.__setattr__(self, "extras", MappingProxyType(extras))


@dataclass(frozen=True, slots=True)
class MetricReport:
    """Result of a single MetricProvider.compute call."""

    provider_id: str
    metric_id: str
    samples: tuple[MetricSample, ...] = ()
    error: Optional[str] = None

    def __post_init__(self) -> None:
        """Normalize samples to a tuple."""
        if not isinstance(self.samples, tuple):
            object.__setattr__(self, "samples", tuple(self.samples))


@runtime_checkable
class MetricProvider(Protocol):
    """Pluggable metric engine that scores source text."""

    @property
    def provider_id(self) -> str:
        """Stable registry key (e.g. ``radon_cc``)."""

    @property
    def metric_id(self) -> str:
        """Metric family id (e.g. ``cyclomatic_complexity``)."""

    def compute(self, source: str, *, path: Optional[str] = None) -> MetricReport:
        """Score ``source``; ``path`` is optional metadata for samples."""


def assert_metric_provider(obj: object) -> MetricProvider:
    """Raise ``TypeError`` if ``obj`` does not satisfy ``MetricProvider``."""
    if not isinstance(obj, MetricProvider):
        raise TypeError(f"object is not a MetricProvider: {type(obj)!r}")
    return obj  # type: ignore[return-value]


class MetricProviderRegistry:
    """Named registry of MetricProvider instances."""

    def __init__(self) -> None:
        self._providers: dict[str, MetricProvider] = {}

    def register(self, provider: MetricProvider) -> None:
        """Register ``provider`` under ``provider.provider_id`` (replace ok)."""
        assert_metric_provider(provider)
        self._providers[provider.provider_id] = provider

    def get(self, provider_id: str) -> MetricProvider:
        """Return a registered provider or raise ``KeyError``."""
        return self._providers[provider_id]

    def has(self, provider_id: str) -> bool:
        """Return True when ``provider_id`` is registered."""
        return provider_id in self._providers

    def provider_ids(self) -> tuple[str, ...]:
        """Return registered provider ids in insertion order."""
        return tuple(self._providers)

    def list_providers(self) -> tuple[MetricProvider, ...]:
        """Return registered providers in insertion order."""
        return tuple(self._providers.values())

    def compute(self, provider_id: str, source: str, *, path: Optional[str] = None) -> MetricReport:
        """Dispatch ``compute`` to the registered provider."""
        return self.get(provider_id).compute(source, path=path)


__all__ = [
    "MetricProvider",
    "MetricProviderRegistry",
    "MetricReport",
    "MetricSample",
    "assert_metric_provider",
]
