# -*- coding: utf-8 -*-
#
# codimension - LSP-backed SemanticProvider (R203)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""LspSemanticProvider: hover / definition / references / outline over LspProcess."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from core.document_snapshot import DocumentSnapshot
from core.semantic import (
    HoverInfo,
    OutlineSymbol,
    SemanticReadiness,
    SymbolLocation,
)
from core.symbol_index import SourceSpan
from infrastructure.lsp_position_codec import LspRange
from infrastructure.lsp_process import LspProcess, LspProcessKey, LspProcessRegistry


@dataclass(frozen=True, slots=True)
class LspSemanticConfig:
    """How to attach an :class:`LspSemanticProvider` to a process key."""

    language_id: str
    workspace_root: str
    command: tuple[str, ...]
    allowlist: tuple[str, ...]
    toolchain: str = ""
    provider_id: str = ""
    language_id_for_did_open: str = ""

    def __post_init__(self) -> None:
        """Fill defaults for provider_id / didOpen languageId."""
        if not self.command:
            raise ValueError("command must be non-empty")
        if not self.provider_id:
            object.__setattr__(
                self,
                "provider_id",
                f"lsp.{self.language_id}",
            )
        if not self.language_id_for_did_open:
            object.__setattr__(self, "language_id_for_did_open", self.language_id)


class LspSemanticProvider:
    """SemanticProvider that lazily owns one :class:`LspProcess` via a registry."""

    def __init__(
        self,
        registry: LspProcessRegistry,
        config: LspSemanticConfig,
        *,
        readiness: SemanticReadiness = SemanticReadiness.READY,
    ) -> None:
        self._registry = registry
        self._config = config
        self._readiness = readiness
        self._opened: set[str] = set()

    @property
    def provider_id(self) -> str:
        """Stable provider id."""
        return self._config.provider_id

    def readiness(self) -> SemanticReadiness:
        """Configured readiness (e.g. C++ DEGRADED without compile_commands)."""
        return self._readiness

    def claims_full_diagnostics(self) -> bool:
        """True only in :attr:`SemanticReadiness.READY`."""
        return self._readiness is SemanticReadiness.READY

    def set_readiness(self, readiness: SemanticReadiness) -> None:
        """Update readiness after workspace probe."""
        self._readiness = readiness

    def _process(self) -> LspProcess:
        key = LspProcessKey(
            self._config.language_id,
            self._config.workspace_root,
            self._config.toolchain,
        )
        proc = self._registry.get_or_create(
            key,
            self._config.command,
            allowlist=self._config.allowlist,
        )
        if not proc.initialized:
            proc.initialize()
        return proc

    def _ensure_open(self, document: DocumentSnapshot) -> LspProcess:
        proc = self._process()
        if document.uri not in self._opened:
            lang = document.language_id or self._config.language_id_for_did_open
            proc.notify(
                "textDocument/didOpen",
                {
                    "textDocument": {
                        "uri": document.uri,
                        "languageId": lang,
                        "version": document.version,
                        "text": document.text,
                    }
                },
            )
            self._opened.add(document.uri)
        return proc

    def hover(self, document: DocumentSnapshot, offset: int) -> HoverInfo | None:
        """LSP ``textDocument/hover`` → :class:`HoverInfo`."""
        proc = self._ensure_open(document)
        pos = proc.codec.to_lsp_position(document, offset)
        result = proc.request(
            "textDocument/hover",
            {"textDocument": {"uri": document.uri}, "position": pos.to_dict()},
        )
        if not result:
            return None
        contents = _markup_to_text(result.get("contents"))
        span = None
        if "range" in result and result["range"]:
            span = proc.codec.to_internal_span(document, LspRange.from_dict(result["range"]))
        return HoverInfo(contents=contents, span=span)

    def definition(self, document: DocumentSnapshot, offset: int) -> tuple[SymbolLocation, ...]:
        """LSP ``textDocument/definition``."""
        return self._locations(document, offset, "textDocument/definition")

    def references(self, document: DocumentSnapshot, offset: int) -> tuple[SymbolLocation, ...]:
        """LSP ``textDocument/references``."""
        proc = self._ensure_open(document)
        pos = proc.codec.to_lsp_position(document, offset)
        result = proc.request(
            "textDocument/references",
            {
                "textDocument": {"uri": document.uri},
                "position": pos.to_dict(),
                "context": {"includeDeclaration": True},
            },
        )
        return _parse_locations(proc, document, result)

    def document_symbols(self, document: DocumentSnapshot) -> tuple[OutlineSymbol, ...]:
        """LSP ``textDocument/documentSymbol``."""
        proc = self._ensure_open(document)
        result = proc.request(
            "textDocument/documentSymbol",
            {"textDocument": {"uri": document.uri}},
        )
        if not result:
            return ()
        return tuple(_parse_outline(proc, document, item) for item in result)

    def _locations(
        self,
        document: DocumentSnapshot,
        offset: int,
        method: str,
    ) -> tuple[SymbolLocation, ...]:
        proc = self._ensure_open(document)
        pos = proc.codec.to_lsp_position(document, offset)
        result = proc.request(
            method,
            {"textDocument": {"uri": document.uri}, "position": pos.to_dict()},
        )
        return _parse_locations(proc, document, result)


def _markup_to_text(contents: Any) -> str:
    if contents is None:
        return ""
    if isinstance(contents, str):
        return contents
    if isinstance(contents, Mapping):
        if "value" in contents:
            return str(contents["value"])
        if "language" in contents and "value" in contents:
            return str(contents["value"])
    if isinstance(contents, Sequence) and not isinstance(contents, (str, bytes)):
        parts = [_markup_to_text(part) for part in contents]
        return "\n".join(p for p in parts if p)
    return str(contents)


def _parse_locations(
    proc: LspProcess,
    document: DocumentSnapshot,
    result: Any,
) -> tuple[SymbolLocation, ...]:
    if not result:
        return ()
    items: list[Any]
    if isinstance(result, Mapping):
        items = [result]
    elif isinstance(result, Sequence):
        items = list(result)
    else:
        return ()
    out: list[SymbolLocation] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        # LocationLink uses targetUri / targetRange
        if "targetUri" in item:
            uri = str(item["targetUri"])
            range_obj = item.get("targetSelectionRange") or item.get("targetRange")
        else:
            uri = str(item.get("uri", document.uri))
            range_obj = item.get("range")
        if not range_obj:
            continue
        # Spans are decoded against the *current* document only when URI matches.
        if uri == document.uri:
            span = proc.codec.to_internal_span(document, LspRange.from_dict(range_obj))
        else:
            # Foreign file: store zero span; R204+ can open the other snapshot.
            span = SourceSpan(0, 0)
        out.append(SymbolLocation(uri=uri, span=span))
    return tuple(out)


def _parse_outline(
    proc: LspProcess,
    document: DocumentSnapshot,
    item: Mapping[str, Any],
) -> OutlineSymbol:
    name = str(item.get("name", ""))
    kind = str(item.get("kind", "unknown"))
    range_obj = item.get("range")
    if range_obj is None:
        loc = item.get("location")
        if isinstance(loc, Mapping):
            range_obj = loc.get("range")
    sel = item.get("selectionRange") or range_obj
    if isinstance(range_obj, Mapping):
        span = proc.codec.to_internal_span(document, LspRange.from_dict(range_obj))
    else:
        span = SourceSpan(0, 0)
    selection = None
    if isinstance(sel, Mapping):
        selection = proc.codec.to_internal_span(document, LspRange.from_dict(sel))
    children_raw = item.get("children") or ()
    children = tuple(_parse_outline(proc, document, child) for child in children_raw if isinstance(child, Mapping))
    return OutlineSymbol(
        name=name,
        kind=kind,
        span=span,
        selection_span=selection,
        children=children,
    )


def build_rust_semantic_provider(
    registry: LspProcessRegistry,
    workspace_root: str,
    *,
    binary: str,
    allowlist: Iterable[str],
    readiness: SemanticReadiness,
    extra_args: Sequence[str] = (),
    toolchain: str = "",
) -> LspSemanticProvider:
    """Factory for rust-analyzer-backed provider."""
    cmd = (binary, *extra_args)
    config = LspSemanticConfig(
        language_id="rust",
        workspace_root=workspace_root,
        command=tuple(cmd),
        allowlist=tuple(allowlist),
        toolchain=toolchain or "cargo",
        provider_id="lsp.rust-analyzer",
        language_id_for_did_open="rust",
    )
    return LspSemanticProvider(registry, config, readiness=readiness)


def build_clangd_semantic_provider(
    registry: LspProcessRegistry,
    workspace_root: str,
    *,
    binary: str,
    allowlist: Iterable[str],
    readiness: SemanticReadiness,
    extra_args: Sequence[str] = (),
    toolchain: str = "",
) -> LspSemanticProvider:
    """Factory for clangd-backed provider."""
    cmd = (binary, *extra_args)
    config = LspSemanticConfig(
        language_id="cpp",
        workspace_root=workspace_root,
        command=tuple(cmd),
        allowlist=tuple(allowlist),
        toolchain=toolchain or "clangd",
        provider_id="lsp.clangd",
        language_id_for_did_open="cpp",
    )
    return LspSemanticProvider(registry, config, readiness=readiness)


__all__ = [
    "LspSemanticConfig",
    "LspSemanticProvider",
    "build_clangd_semantic_provider",
    "build_rust_semantic_provider",
]
