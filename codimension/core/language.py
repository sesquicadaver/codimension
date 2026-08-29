# -*- coding: utf-8 -*-
#
# codimension - polyglot language service contracts (R200/R203/R205)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""LanguageDescriptor, capabilities, and LanguageServiceRegistry (R200–R205).

Qt-free polyglot attach points. Document buffers / position codec are R201;
LSP stdio process client is R202; Rust/C++ descriptors + SemanticProvider are
R203; Tree-sitter StructuralProvider is R205. UI must query
:class:`LanguageCapability`, never ``if language == …``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from .semantic import SemanticProvider
from .structural import StructuralProvider


class LanguageCapability(str, Enum):
    """Stable capability tags for language services (UI gates on these)."""

    OUTLINE = "outline"
    DIAGNOSTICS = "diagnostics"
    SEMANTIC_TOKENS = "semantic_tokens"
    COMPLETION = "completion"
    HOVER = "hover"
    DEFINITION = "definition"
    REFERENCES = "references"
    RENAME = "rename"
    FORMAT = "format"
    STRUCTURAL_GRAPH = "structural_graph"
    FFI_BINDINGS = "ffi_bindings"
    BUILD_TASKS = "build_tasks"


@dataclass(frozen=True, slots=True)
class LanguageDescriptor:
    """Declarative identity for a language (extensions + workspace roots)."""

    language_id: str
    extensions: frozenset[str]
    root_markers: tuple[str, ...] = ()
    server_name: str = ""

    def __post_init__(self) -> None:
        """Reject empty language_id."""
        if not self.language_id.strip():
            raise ValueError("language_id must be non-empty")


@dataclass(frozen=True, slots=True)
class LanguageService:
    """Registered language surface: descriptor + capabilities + optional providers.

    Provider slots stay ``None`` / empty until later R-tasks (FFI, tasks).
    R203 fills ``semantic`` for Rust/C++ via LSP; R205 fills ``structural``.
    """

    descriptor: LanguageDescriptor
    capabilities: frozenset[LanguageCapability]
    service_id: str = ""
    semantic: SemanticProvider | None = None
    structural: StructuralProvider | None = None
    bindings: tuple[object, ...] = ()
    tasks: object | None = None

    def __post_init__(self) -> None:
        """Derive ``service_id`` from ``language_id`` when omitted."""
        caps = frozenset(self.capabilities)
        object.__setattr__(self, "capabilities", caps)
        if not self.service_id:
            object.__setattr__(self, "service_id", self.descriptor.language_id)

    def has_capability(self, capability: LanguageCapability) -> bool:
        """Return True when ``capability`` is advertised."""
        return capability in self.capabilities


#: Built-in Python descriptor (existing brief/flow/SymbolIndex pipeline).
PYTHON_DESCRIPTOR = LanguageDescriptor(
    language_id="python",
    extensions=frozenset({".py", ".pyw", ".pyi"}),
    root_markers=("pyproject.toml", "setup.py", "setup.cfg", ".cdm3"),
)

#: Headless capabilities already backed by SymbolIndex / brief (no LSP).
PYTHON_HEADLESS_CAPABILITIES: frozenset[LanguageCapability] = frozenset(
    {
        LanguageCapability.OUTLINE,
        LanguageCapability.DEFINITION,
        LanguageCapability.REFERENCES,
    }
)

#: Rust descriptor (rust-analyzer).
RUST_DESCRIPTOR = LanguageDescriptor(
    language_id="rust",
    extensions=frozenset({".rs"}),
    root_markers=("Cargo.toml", "rust-project.json"),
    server_name="rust-analyzer",
)

#: C/C++ descriptor (clangd). ``.h`` language mode still comes from compile DB.
CPP_DESCRIPTOR = LanguageDescriptor(
    language_id="cpp",
    extensions=frozenset(
        {
            ".cc",
            ".cpp",
            ".cxx",
            ".c",
            ".hh",
            ".hpp",
            ".hxx",
            ".h",
            ".ixx",
            ".cppm",
        }
    ),
    root_markers=("compile_commands.json", "CMakeLists.txt"),
    server_name="clangd",
)

#: LSP-backed editor capabilities shared by Rust / C++ in Stage 1.
LSP_EDITOR_CAPABILITIES: frozenset[LanguageCapability] = frozenset(
    {
        LanguageCapability.OUTLINE,
        LanguageCapability.DIAGNOSTICS,
        LanguageCapability.HOVER,
        LanguageCapability.DEFINITION,
        LanguageCapability.REFERENCES,
        LanguageCapability.COMPLETION,
        LanguageCapability.RENAME,
        LanguageCapability.FORMAT,
        LanguageCapability.SEMANTIC_TOKENS,
    }
)


def make_python_language_service() -> LanguageService:
    """Return the R200 Python stub service (no LSP providers)."""
    return LanguageService(
        descriptor=PYTHON_DESCRIPTOR,
        capabilities=PYTHON_HEADLESS_CAPABILITIES,
        service_id="python.headless",
    )


def _with_structural_capability(
    base: frozenset[LanguageCapability],
    structural: StructuralProvider | None,
) -> frozenset[LanguageCapability]:
    """Advertise STRUCTURAL_GRAPH only when a structural provider is bound."""
    if structural is None:
        return base
    return frozenset(base | {LanguageCapability.STRUCTURAL_GRAPH})


def make_rust_language_service(
    semantic: SemanticProvider | None = None,
    structural: StructuralProvider | None = None,
) -> LanguageService:
    """Return a Rust language service (LSP semantic + optional Tree-sitter)."""
    return LanguageService(
        descriptor=RUST_DESCRIPTOR,
        capabilities=_with_structural_capability(LSP_EDITOR_CAPABILITIES, structural),
        service_id="rust.lsp",
        semantic=semantic,
        structural=structural,
    )


def make_cpp_language_service(
    semantic: SemanticProvider | None = None,
    structural: StructuralProvider | None = None,
) -> LanguageService:
    """Return a C++ language service (LSP semantic + optional Tree-sitter)."""
    return LanguageService(
        descriptor=CPP_DESCRIPTOR,
        capabilities=_with_structural_capability(LSP_EDITOR_CAPABILITIES, structural),
        service_id="cpp.lsp",
        semantic=semantic,
        structural=structural,
    )


@runtime_checkable
class LanguageServiceLike(Protocol):
    """Minimal protocol for registry entries (matches :class:`LanguageService`)."""

    @property
    def service_id(self) -> str:
        """Stable registry key."""

    @property
    def descriptor(self) -> LanguageDescriptor:
        """Language descriptor."""

    @property
    def capabilities(self) -> frozenset[LanguageCapability]:
        """Advertised capabilities."""


class LanguageServiceRegistry:
    """Named registry of :class:`LanguageService` instances."""

    def __init__(self) -> None:
        self._services: dict[str, LanguageService] = {}

    def register(self, service: LanguageService) -> None:
        """Register ``service`` under ``service.service_id`` (replace ok)."""
        if not isinstance(service, LanguageService):
            raise TypeError(f"expected LanguageService, got {type(service)!r}")
        self._services[service.service_id] = service

    def unregister(self, service_id: str) -> None:
        """Remove a service if present."""
        self._services.pop(service_id, None)

    def get(self, service_id: str) -> LanguageService:
        """Return a registered service or raise ``KeyError``."""
        return self._services[service_id]

    def has(self, service_id: str) -> bool:
        """Return True when ``service_id`` is registered."""
        return service_id in self._services

    def get_by_language_id(self, language_id: str) -> tuple[LanguageService, ...]:
        """Return services whose descriptor ``language_id`` matches."""
        return tuple(s for s in self._services.values() if s.descriptor.language_id == language_id)

    def service_ids(self) -> tuple[str, ...]:
        """Return registered service ids in insertion order."""
        return tuple(self._services)

    def list_services(self) -> tuple[LanguageService, ...]:
        """Return registered services in insertion order."""
        return tuple(self._services.values())

    def clear(self) -> None:
        """Remove all services."""
        self._services.clear()


__all__ = [
    "CPP_DESCRIPTOR",
    "LanguageCapability",
    "LanguageDescriptor",
    "LanguageService",
    "LanguageServiceLike",
    "LanguageServiceRegistry",
    "LSP_EDITOR_CAPABILITIES",
    "PYTHON_DESCRIPTOR",
    "PYTHON_HEADLESS_CAPABILITIES",
    "RUST_DESCRIPTOR",
    "make_cpp_language_service",
    "make_python_language_service",
    "make_rust_language_service",
]
