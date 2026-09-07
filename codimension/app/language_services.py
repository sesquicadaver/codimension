# -*- coding: utf-8 -*-
#
# codimension - language services manager (R200–R208 / R230)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""LanguageServiceManager — lifecycle façade for polyglot services (R200–R230).

Headless: no Qt. When ``FLAG_LANGUAGE_SERVICES`` is off, :meth:`ensure_defaults`
and :meth:`attach_workspace` are no-ops (empty registry). When on, registers
the Python headless stub and optionally Rust/C++ services for the workspace.

Owns an :class:`~infrastructure.lsp_process.LspProcessRegistry` shut down on
:meth:`detach_workspace` / :meth:`shutdown`. Rust/C++ LSP processes spawn only
when absolute binaries are supplied (env ``CDM_RUST_ANALYZER`` /
``CDM_CLANGD`` or explicit kwargs) and pass ``LANGUAGE_SERVER_SPAWN``.
Without binaries, marker-backed workspaces still get Tree-sitter / FFI /
Task providers (no semantic LSP).

R230: IDE composition roots call :meth:`attach_workspace` /
:meth:`detach_workspace` on project load/unload.
"""

from __future__ import annotations

import os
from typing import Iterable, Mapping, Optional, Sequence

from core.bindings import BindingProvider
from core.feature_flags import (
    FLAG_LANGUAGE_SERVICES,
    FeatureFlagsStore,
    is_feature_enabled,
)
from core.language import (
    CPP_DESCRIPTOR,
    RUST_DESCRIPTOR,
    LanguageServiceRegistry,
    make_cpp_language_service,
    make_python_language_service,
    make_rust_language_service,
)
from core.language_workspace import (
    assess_cpp_semantic_readiness,
    assess_rust_semantic_readiness,
    find_compile_commands_json,
)
from core.structural import StructuralProvider
from core.tasks import TaskProvider
from infrastructure.build_tasks import make_cpp_task_provider, make_rust_task_provider
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

#: Absolute path to rust-analyzer (optional; spawn-gated).
ENV_RUST_ANALYZER = "CDM_RUST_ANALYZER"
#: Absolute path to clangd (optional; spawn-gated).
ENV_CLANGD = "CDM_CLANGD"
#: Extra absolute binaries for LANGUAGE_SERVER_SPAWN (``os.pathsep``-separated).
ENV_LANGUAGE_SERVER_ALLOWLIST = "CDM_LANGUAGE_SERVER_ALLOWLIST"


def is_language_services_enabled(
    *,
    store: Optional[FeatureFlagsStore] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> bool:
    """Return True when the polyglot language-services flag is on."""
    return bool(is_feature_enabled(FLAG_LANGUAGE_SERVICES, store=store, environ=environ))


def _env_absolute_binary(environ: Mapping[str, str], key: str) -> str | None:
    """Return a configured absolute binary path, or ``None`` when unset/invalid."""
    raw = (environ.get(key) or "").strip()
    if not raw or not os.path.isabs(raw):
        return None
    return raw


def _env_allowlist(environ: Mapping[str, str], *extra: str) -> tuple[str, ...]:
    """Merge ``CDM_LANGUAGE_SERVER_ALLOWLIST`` entries with ``extra`` absolutes."""
    found: list[str] = []
    seen: set[str] = set()
    raw = (environ.get(ENV_LANGUAGE_SERVER_ALLOWLIST) or "").strip()
    parts = [p.strip() for p in raw.split(os.pathsep)] if raw else []
    for candidate in (*parts, *extra):
        path = (candidate or "").strip()
        if not path or not os.path.isabs(path) or path in seen:
            continue
        seen.add(path)
        found.append(path)
    return tuple(found)


def _has_any_marker(workspace_root: str, markers: Sequence[str]) -> bool:
    """True when any marker exists directly under ``workspace_root``."""
    root = os.path.abspath(os.path.expanduser(workspace_root))
    for marker in markers:
        if os.path.exists(os.path.join(root, marker)):
            return True
    return False


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
        self._workspace_root: str | None = None

    @property
    def registry(self) -> LanguageServiceRegistry:
        """Underlying service registry."""
        return self._registry

    @property
    def lsp_processes(self) -> LspProcessRegistry:
        """LSP stdio process registry (R202)."""
        return self._lsp_processes

    @property
    def workspace_root(self) -> str | None:
        """Absolute workspace root from the last successful :meth:`attach_workspace`."""
        return self._workspace_root

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

    @staticmethod
    def _optional_tasks(language_id: str, attach: bool) -> TaskProvider | None:
        """Return Cargo or CMake/Ninja/CTest providers when requested."""
        if not attach:
            return None
        lid = language_id.strip().lower()
        if lid == "rust":
            return make_rust_task_provider()
        if lid == "cpp":
            return make_cpp_task_provider()
        return None

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
        attach_tasks: bool = True,
    ) -> str:
        """Register ``rust.lsp`` with rust-analyzer semantic provider.

        Readiness is READY when ``Cargo.toml`` / ``rust-project.json`` exists
        at ``workspace_root``, else DEGRADED. Optional Tree-sitter /
        PyO3 binding / Cargo task providers advertise
        ``STRUCTURAL_GRAPH`` / ``FFI_BINDINGS`` / ``BUILD_TASKS``.
        Task providers only discover argv plans — they do not run on register.
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
        tasks = self._optional_tasks("rust", attach_tasks)
        service = make_rust_language_service(
            semantic=semantic,
            structural=structural,
            bindings=bindings,
            tasks=tasks,
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
        attach_tasks: bool = True,
    ) -> str:
        """Register ``cpp.lsp`` with clangd semantic provider.

        Readiness is READY only when ``compile_commands.json`` is found;
        otherwise DEGRADED (no full-diagnostics claim). Optional Tree-sitter /
        pybind11+CPython / CMake·Ninja·CTest attach mirrors
        :meth:`register_rust_lsp`. clangd is never used as a build runner.
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
        tasks = self._optional_tasks("cpp", attach_tasks)
        service = make_cpp_language_service(
            semantic=semantic,
            structural=structural,
            bindings=bindings,
            tasks=tasks,
        )
        self._registry.register(service)
        return str(service.service_id)

    def _register_rust_headless(
        self,
        workspace_root: str,
        *,
        attach_structural: bool,
        attach_bindings: bool,
        attach_tasks: bool,
    ) -> str:
        """Register ``rust.lsp`` without a SemanticProvider (marker-only workspace)."""
        del workspace_root  # readiness unused without LSP; markers already gated attach
        service = make_rust_language_service(
            semantic=None,
            structural=self._optional_structural("rust", attach_structural),
            bindings=self._optional_bindings("rust", attach_bindings),
            tasks=self._optional_tasks("rust", attach_tasks),
        )
        self._registry.register(service)
        return str(service.service_id)

    def _register_cpp_headless(
        self,
        workspace_root: str,
        *,
        attach_structural: bool,
        attach_bindings: bool,
        attach_tasks: bool,
    ) -> str:
        """Register ``cpp.lsp`` without a SemanticProvider (marker-only workspace)."""
        del workspace_root
        service = make_cpp_language_service(
            semantic=None,
            structural=self._optional_structural("cpp", attach_structural),
            bindings=self._optional_bindings("cpp", attach_bindings),
            tasks=self._optional_tasks("cpp", attach_tasks),
        )
        self._registry.register(service)
        return str(service.service_id)

    def attach_workspace(
        self,
        workspace_root: str,
        *,
        store: Optional[FeatureFlagsStore] = None,
        environ: Optional[Mapping[str, str]] = None,
        rust_binary: str | None = None,
        cpp_binary: str | None = None,
        allowlist: Iterable[str] | None = None,
        attach_structural: bool = True,
        attach_bindings: bool = True,
        attach_tasks: bool = True,
    ) -> bool:
        """Bind language services to ``workspace_root`` (R230).

        Clears any previous workspace first. When the feature flag is off,
        detaches and returns ``False``. When on: Python stub + optional
        Rust/C++ services for descriptor root markers. LSP semantic providers
        register only when an absolute binary is available (kwargs or env).

        Returns:
            ``True`` when the flag is on and defaults were applied.
        """
        env = environ if environ is not None else os.environ
        self.detach_workspace()
        if not self.ensure_defaults(store=store, environ=env):
            return False

        root = os.path.abspath(os.path.expanduser(workspace_root))
        rust_bin = rust_binary if rust_binary is not None else _env_absolute_binary(env, ENV_RUST_ANALYZER)
        cpp_bin = cpp_binary if cpp_binary is not None else _env_absolute_binary(env, ENV_CLANGD)
        if allowlist is None:
            allowed = _env_allowlist(env, *(p for p in (rust_bin, cpp_bin) if p))
        else:
            allowed = tuple(str(a) for a in allowlist)

        if _has_any_marker(root, RUST_DESCRIPTOR.root_markers):
            if rust_bin and allowed:
                self.register_rust_lsp(
                    root,
                    binary=rust_bin,
                    allowlist=allowed,
                    attach_structural=attach_structural,
                    attach_bindings=attach_bindings,
                    attach_tasks=attach_tasks,
                )
            else:
                self._register_rust_headless(
                    root,
                    attach_structural=attach_structural,
                    attach_bindings=attach_bindings,
                    attach_tasks=attach_tasks,
                )

        cpp_markers = _has_any_marker(root, CPP_DESCRIPTOR.root_markers) or (
            find_compile_commands_json(root) is not None
        )
        if cpp_markers:
            if cpp_bin and allowed:
                self.register_cpp_lsp(
                    root,
                    binary=cpp_bin,
                    allowlist=allowed,
                    attach_structural=attach_structural,
                    attach_bindings=attach_bindings,
                    attach_tasks=attach_tasks,
                )
            else:
                self._register_cpp_headless(
                    root,
                    attach_structural=attach_structural,
                    attach_bindings=attach_bindings,
                    attach_tasks=attach_tasks,
                )

        self._workspace_root = root
        return True

    def detach_workspace(self) -> None:
        """Shut down LSP processes and clear services for the current workspace."""
        self.shutdown()

    def shutdown(self) -> None:
        """Shut down LSP processes and clear registered services."""
        self._lsp_processes.shutdown_all()
        self._registry.clear()
        self._workspace_root = None


__all__ = [
    "ENV_CLANGD",
    "ENV_LANGUAGE_SERVER_ALLOWLIST",
    "ENV_RUST_ANALYZER",
    "LanguageServiceManager",
    "is_language_services_enabled",
]
