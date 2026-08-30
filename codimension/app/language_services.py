# -*- coding: utf-8 -*-
#
# codimension - language services manager (R200–R206)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""LanguageServiceManager — lifecycle façade for polyglot services (R200–R206).

Headless: no Qt. When ``FLAG_LANGUAGE_SERVICES`` is off, :meth:`ensure_defaults`
is a no-op (empty registry). When on, registers the Python headless stub.
Owns an :class:`~infrastructure.lsp_process.LspProcessRegistry` shut down on
workspace unload. Rust/C++ LSP services are registered explicitly via
:meth:`register_rust_lsp` / :meth:`register_cpp_lsp` (spawn-gated allowlist).
Tree-sitter structural providers attach via ``attach_structural=True`` (R205)
when grammars are installed. FFI binding providers attach via
``attach_bindings=True`` (R206).
"""

from __future__ import annotations

from typing import Iterable, Mapping, Optional, Sequence

from core.bindings import BindingProvider
from core.feature_flags import (
    FLAG_LANGUAGE_SERVICES,
    FeatureFlagsStore,
    is_feature_enabled,
)
from core.language import (
    LanguageServiceRegistry,
    make_cpp_language_service,
    make_python_language_service,
    make_rust_language_service,
)
from core.language_workspace import (
    assess_cpp_semantic_readiness,
    assess_rust_semantic_readiness,
)
from core.structural import StructuralProvider
from infrastructure.ffi_bindings import (
    CPythonBindingProvider,
    Pybind11BindingProvider,
    PyO3BindingProvider,
)
from infrastructure.lsp_process import LspProcessRegistry
from infrastructure.lsp_semantic import (
    build_clangd_semantic_provider,
    build_rust_semantic_provider,
)
from infrastructure.tree_sitter_structural import try_build_tree_sitter_structural_provider


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

    @staticmethod
    def _optional_structural(language_id: str, attach: bool) -> StructuralProvider | None:
        """Load Tree-sitter structural provider when requested and available."""
        if not attach:
            return None
        return try_build_tree_sitter_structural_provider(language_id)

    @staticmethod
    def _optional_bindings(language_id: str, attach: bool) -> tuple[BindingProvider, ...]:
        """Return framework extractors for ``language_id`` when requested."""
        if not attach:
            return ()
        lid = language_id.strip().lower()
        if lid == "rust":
            return (PyO3BindingProvider(),)
        if lid == "cpp":
            return (Pybind11BindingProvider(), CPythonBindingProvider())
        return ()

    def register_rust_lsp(
        self,
        workspace_root: str,
        *,
        binary: str,
        allowlist: Iterable[str],
        extra_args: Sequence[str] = (),
        toolchain: str = "",
        attach_structural: bool = True,
        attach_bindings: bool = True,
    ) -> str:
        """Register ``rust.lsp`` with rust-analyzer semantic provider.

        Readiness is READY when ``Cargo.toml`` / ``rust-project.json`` exists
        at ``workspace_root``, else DEGRADED. Optional Tree-sitter /
        PyO3 binding providers advertise ``STRUCTURAL_GRAPH`` / ``FFI_BINDINGS``.
        """
        readiness = assess_rust_semantic_readiness(workspace_root)
        semantic = build_rust_semantic_provider(
            self._lsp_processes,
            workspace_root,
            binary=binary,
            allowlist=allowlist,
            readiness=readiness,
            extra_args=extra_args,
            toolchain=toolchain,
        )
        structural = self._optional_structural("rust", attach_structural)
        bindings = self._optional_bindings("rust", attach_bindings)
        service = make_rust_language_service(
            semantic=semantic,
            structural=structural,
            bindings=bindings,
        )
        self._registry.register(service)
        return str(service.service_id)

    def register_cpp_lsp(
        self,
        workspace_root: str,
        *,
        binary: str,
        allowlist: Iterable[str],
        extra_args: Sequence[str] = (),
        toolchain: str = "",
        attach_structural: bool = True,
        attach_bindings: bool = True,
    ) -> str:
        """Register ``cpp.lsp`` with clangd semantic provider.

        Readiness is READY only when ``compile_commands.json`` is found;
        otherwise DEGRADED (no full-diagnostics claim). Optional Tree-sitter /
        pybind11+CPython binding attach mirrors :meth:`register_rust_lsp`.
        """
        readiness = assess_cpp_semantic_readiness(workspace_root)
        semantic = build_clangd_semantic_provider(
            self._lsp_processes,
            workspace_root,
            binary=binary,
            allowlist=allowlist,
            readiness=readiness,
            extra_args=extra_args,
            toolchain=toolchain,
        )
        structural = self._optional_structural("cpp", attach_structural)
        bindings = self._optional_bindings("cpp", attach_bindings)
        service = make_cpp_language_service(
            semantic=semantic,
            structural=structural,
            bindings=bindings,
        )
        self._registry.register(service)
        return str(service.service_id)

    def shutdown(self) -> None:
        """Shut down LSP processes and clear registered services."""
        self._lsp_processes.shutdown_all()
        self._registry.clear()


__all__ = [
    "LanguageServiceManager",
    "is_language_services_enabled",
]
