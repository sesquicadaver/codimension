# -*- coding: utf-8 -*-
#
# codimension - language services manager (R200/R202)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""LanguageServiceManager — lifecycle façade for polyglot services (R200/R202).

Headless: no Qt. When ``FLAG_LANGUAGE_SERVICES`` is off, :meth:`ensure_defaults`
is a no-op (empty registry). When on, registers the Python headless stub.
Owns an :class:`~infrastructure.lsp_process.LspProcessRegistry` shut down on
workspace unload.
"""

from __future__ import annotations

from typing import Mapping, Optional

from core.feature_flags import (
    FLAG_LANGUAGE_SERVICES,
    FeatureFlagsStore,
    is_feature_enabled,
)
from core.language import (
    LanguageServiceRegistry,
    make_python_language_service,
)
from infrastructure.lsp_process import LspProcessRegistry


def is_language_services_enabled(
    *,
    store: Optional[FeatureFlagsStore] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> bool:
    """Return True when the polyglot language-services flag is on."""
    return bool(is_feature_enabled(FLAG_LANGUAGE_SERVICES, store=store, environ=environ))


class LanguageServiceManager:
    """Owns a :class:`LanguageServiceRegistry` gated by feature flags."""

    def __init__(
        self,
        registry: Optional[LanguageServiceRegistry] = None,
        lsp_processes: Optional[LspProcessRegistry] = None,
    ) -> None:
        """Bind optional registries (creates fresh ones when omitted)."""
        self._registry = registry if registry is not None else LanguageServiceRegistry()
        self._lsp_processes = lsp_processes if lsp_processes is not None else LspProcessRegistry()

    @property
    def registry(self) -> LanguageServiceRegistry:
        """Underlying service registry."""
        return self._registry

    @property
    def lsp_processes(self) -> LspProcessRegistry:
        """LSP stdio process registry (R202)."""
        return self._lsp_processes

    def ensure_defaults(
        self,
        *,
        store: Optional[FeatureFlagsStore] = None,
        environ: Optional[Mapping[str, str]] = None,
    ) -> bool:
        """Register built-in Python stub when the feature flag is enabled.

        Returns:
            ``True`` when defaults were applied; ``False`` when the flag is off
            (registry left unchanged — typically empty for a fresh manager).
        """
        if not is_language_services_enabled(store=store, environ=environ):
            return False
        service = make_python_language_service()
        if not self._registry.has(service.service_id):
            self._registry.register(service)
        return True

    def shutdown(self) -> None:
        """Shut down LSP processes and clear registered services."""
        self._lsp_processes.shutdown_all()
        self._registry.clear()


__all__ = [
    "LanguageServiceManager",
    "is_language_services_enabled",
]
