# -*- coding: utf-8 -*-
#
# codimension - LSP-backed SemanticProvider (R203 / R224)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""LspSemanticProvider: hover / definition / references / outline over LspProcess.

R224: foreign-URI locations and workspace edits decode spans via
:class:`~core.document_store.DocumentStore` (open buffers + ``file://`` load).

R233: document sync tracks :meth:`LspProcess.ensure_initialized` generation so
a crash+restart never reuses stale ``_opened`` state or skips handshake.

R245: refuse regressive ``didChange`` versions — remigrate via didClose+didOpen.

R253: semantic RPC is generation-atomic — ``didOpen``/``didChange`` and the
following ``request`` must land on the same handshake generation; a restart
between sync and request retries sync before the query.

R262: document ``notify`` is generation-pinned too — a restart during sync
clears ``_opened`` and re-``didOpen`` instead of sending ``didChange`` to a
virgin process.

R266: server ranges decode via ``try_parse_lsp_range`` (never raises); bad
payloads become ``UNRESOLVED`` / omitted hover spans.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

from core.document_snapshot import DocumentSnapshot, TextEdit
from core.document_store import DocumentStore, ResolutionStatus, canonicalize_document_uri
from core.semantic import (
    HoverInfo,
    OutlineSymbol,
    SemanticReadiness,
    SymbolLocation,
    WorkspaceTextEdit,
)
from core.symbol_index import SourceSpan
from infrastructure.file_uri import make_workspace_document_loader
from infrastructure.lsp_position_codec import try_parse_lsp_range
from infrastructure.lsp_process import LspProcess, LspProcessKey, LspProcessRegistry, LspProtocolError

# Restarts between sync and request are rare; bound retries to avoid livelock.
_SYNC_REQUEST_ATTEMPTS = 5


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
        document_store: DocumentStore | None = None,
    ) -> None:
        self._registry = registry
        self._config = config
        self._readiness = readiness
        # uri → last version synced to the language server (didOpen / didChange).
        self._opened: dict[str, int] = {}
        # Last LspProcess.generation observed; mismatch clears ``_opened`` (R233).
        self._server_generation: int = 0
        # R235: never use ``document_store or …``; identity check keeps empty shared stores.
        if document_store is not None:
            self._documents = document_store
        else:
            self._documents = DocumentStore(loader=make_workspace_document_loader(config.workspace_root))

    @property
    def document_store(self) -> DocumentStore:
        """Store used to resolve foreign URIs for span decoding (R224)."""
        return self._documents

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

    def _attach_process(self) -> LspProcess:
        """Return a live initialized process; clear ``_opened`` on generation bump."""
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
        generation = proc.ensure_initialized()
        if generation != self._server_generation:
            # Restart / first handshake: previous document state is gone.
            self._opened.clear()
            self._server_generation = generation
        return proc

    def _process(self) -> LspProcess:
        """Compatibility alias for tests that reach into the attached process."""
        return self._attach_process()

    def _forget_opened(self, proc: LspProcess) -> None:
        """Drop local open tracking after a handshake generation change (R262)."""
        self._opened.clear()
        self._server_generation = proc.generation

    def _generation_resync_needed(self, exc: BaseException, proc: LspProcess, gen: int) -> bool:
        """True when sync/request must clear opens and retry on a new generation."""
        if proc.generation != gen:
            return True
        return isinstance(exc, LspProtocolError) and "generation changed" in str(exc)

    def _sync_document(
        self,
        proc: LspProcess,
        document: DocumentSnapshot,
        *,
        expect_generation: int,
    ) -> None:
        """Push ``document`` to ``proc`` (didOpen / didChange / remigrate).

        R262: every notify is pinned to ``expect_generation`` so a mid-sync
        restart cannot deliver ``didChange`` to a virgin language server.
        """
        uri = document.uri
        opened_version = self._opened.get(uri)
        # R245: never send a regressive didChange — remigrate via close+open.
        if opened_version is not None and document.version < opened_version:
            try:
                proc.notify(
                    "textDocument/didClose",
                    {"textDocument": {"uri": uri}},
                    expect_generation=expect_generation,
                )
            except Exception:  # noqa: BLE001 — best-effort before reopen
                pass
            self._opened.pop(uri, None)
            opened_version = None

        if uri not in self._opened:
            lang = document.language_id or self._config.language_id_for_did_open
            proc.notify(
                "textDocument/didOpen",
                {
                    "textDocument": {
                        "uri": uri,
                        "languageId": lang,
                        "version": document.version,
                        "text": document.text,
                    }
                },
                expect_generation=expect_generation,
            )
            self._opened[uri] = document.version
            return

        if self._opened[uri] != document.version:
            proc.notify(
                "textDocument/didChange",
                {
                    "textDocument": {"uri": uri, "version": document.version},
                    "contentChanges": [{"text": document.text}],
                },
                expect_generation=expect_generation,
            )
            self._opened[uri] = document.version

    def _ensure_open(self, document: DocumentSnapshot) -> LspProcess:
        """Ensure the server has the current document text (didOpen or didChange)."""
        self._documents.put(document)
        last_error: LspProtocolError | None = None
        for _ in range(_SYNC_REQUEST_ATTEMPTS):
            proc = self._attach_process()
            gen = proc.generation
            try:
                self._sync_document(proc, document, expect_generation=gen)
            except LspProtocolError as exc:
                last_error = exc
                if self._generation_resync_needed(exc, proc, gen):
                    self._forget_opened(proc)
                    continue
                raise
            if proc.generation != gen:
                self._forget_opened(proc)
                continue
            return proc
        if last_error is not None:
            raise last_error
        raise LspProtocolError("LSP document sync raced with process restart")

    def _sync_and_request(
        self,
        document: DocumentSnapshot,
        method: str,
        params_for: Callable[[LspProcess], Any],
        *,
        timeout: float | None = None,
    ) -> tuple[Any, LspProcess]:
        """Sync the document then request on the same handshake generation (R253 / R262).

        If ``notify``/``request`` (or a concurrent peer) restarts the language
        server after attach, clear open tracking and re-``didOpen`` before the
        semantic query so a virgin generation never sees ``didChange`` first.
        """
        self._documents.put(document)
        last_error: LspProtocolError | None = None
        for _ in range(_SYNC_REQUEST_ATTEMPTS):
            proc = self._attach_process()
            gen = proc.generation
            try:
                self._sync_document(proc, document, expect_generation=gen)
            except LspProtocolError as exc:
                last_error = exc
                if self._generation_resync_needed(exc, proc, gen):
                    self._forget_opened(proc)
                    continue
                raise
            if proc.generation != gen:
                self._forget_opened(proc)
                continue
            params = params_for(proc)
            try:
                result = proc.request(
                    method,
                    params,
                    timeout=timeout,
                    expect_generation=gen,
                )
            except LspProtocolError as exc:
                last_error = exc
                if self._generation_resync_needed(exc, proc, gen):
                    self._forget_opened(proc)
                    continue
                raise
            if proc.generation != gen:
                # Concurrent peer restarted after our write — retry.
                self._forget_opened(proc)
                continue
            return result, proc
        if last_error is not None:
            raise last_error
        raise LspProtocolError(f"LSP document sync raced with process restart for {method}")

    def sync_document(self, document: DocumentSnapshot) -> None:
        """Push buffer text to the language server (didOpen or full didChange)."""
        self._ensure_open(document)

    def close_document(self, document: DocumentSnapshot) -> None:
        """Notify ``textDocument/didClose`` and drop local open tracking."""
        uri = document.uri
        if uri not in self._opened:
            return
        # Pop before touching the process so a restart clear cannot resurrect
        # tracking, and so we can skip didClose on a virgin post-restart server.
        self._opened.pop(uri, None)
        self._documents.discard(uri)
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
        prev_generation = self._server_generation
        generation = proc.ensure_initialized()
        if generation != prev_generation:
            # Fresh server after crash — nothing to close on the new process.
            self._opened.clear()
            self._server_generation = generation
            return
        proc.notify(
            "textDocument/didClose",
            {"textDocument": {"uri": uri}},
            expect_generation=generation,
        )

    def hover(self, document: DocumentSnapshot, offset: int) -> HoverInfo | None:
        """LSP ``textDocument/hover`` → :class:`HoverInfo`."""

        def params(proc: LspProcess) -> dict[str, Any]:
            pos = proc.codec.to_lsp_position(document, offset)
            return {"textDocument": {"uri": document.uri}, "position": pos.to_dict()}

        result, proc = self._sync_and_request(document, "textDocument/hover", params)
        if not result:
            return None
        contents = _markup_to_text(result.get("contents"))
        span = None
        if "range" in result and result["range"]:
            lsp_range = try_parse_lsp_range(result["range"])
            if lsp_range is not None:
                span = proc.codec.to_internal_span(document, lsp_range)
        return HoverInfo(contents=contents, span=span)

    def definition(self, document: DocumentSnapshot, offset: int) -> tuple[SymbolLocation, ...]:
        """LSP ``textDocument/definition``."""
        return self._locations(document, offset, "textDocument/definition")

    def references(self, document: DocumentSnapshot, offset: int) -> tuple[SymbolLocation, ...]:
        """LSP ``textDocument/references``."""

        def params(proc: LspProcess) -> dict[str, Any]:
            pos = proc.codec.to_lsp_position(document, offset)
            return {
                "textDocument": {"uri": document.uri},
                "position": pos.to_dict(),
                "context": {"includeDeclaration": True},
            }

        result, proc = self._sync_and_request(document, "textDocument/references", params)
        return _parse_locations(proc, document, result, store=self._documents)

    def document_symbols(self, document: DocumentSnapshot) -> tuple[OutlineSymbol, ...]:
        """LSP ``textDocument/documentSymbol``."""

        def params(_proc: LspProcess) -> dict[str, Any]:
            return {"textDocument": {"uri": document.uri}}

        result, proc = self._sync_and_request(document, "textDocument/documentSymbol", params)
        if not result:
            return ()
        return tuple(_parse_outline(proc, document, item) for item in result)

    def format_document(self, document: DocumentSnapshot) -> tuple[WorkspaceTextEdit, ...]:
        """LSP ``textDocument/formatting`` → preview edits."""

        def params(_proc: LspProcess) -> dict[str, Any]:
            return {
                "textDocument": {"uri": document.uri},
                "options": {"tabSize": 4, "insertSpaces": True},
            }

        result, proc = self._sync_and_request(document, "textDocument/formatting", params)
        return _parse_text_edits(proc, document, document.uri, result, store=self._documents)

    def rename_preview(
        self,
        document: DocumentSnapshot,
        offset: int,
        new_name: str,
    ) -> tuple[WorkspaceTextEdit, ...]:
        """LSP ``textDocument/rename`` → preview edits (caller applies)."""

        def params(proc: LspProcess) -> dict[str, Any]:
            pos = proc.codec.to_lsp_position(document, offset)
            return {
                "textDocument": {"uri": document.uri},
                "position": pos.to_dict(),
                "newName": new_name,
            }

        result, proc = self._sync_and_request(document, "textDocument/rename", params)
        return _parse_workspace_edit(proc, document, result, store=self._documents)

    def _locations(
        self,
        document: DocumentSnapshot,
        offset: int,
        method: str,
    ) -> tuple[SymbolLocation, ...]:
        def params(proc: LspProcess) -> dict[str, Any]:
            pos = proc.codec.to_lsp_position(document, offset)
            return {"textDocument": {"uri": document.uri}, "position": pos.to_dict()}

        result, proc = self._sync_and_request(document, method, params)
        return _parse_locations(proc, document, result, store=self._documents)


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


def _span_for_uri(
    proc: LspProcess,
    document: DocumentSnapshot,
    uri: str,
    range_obj: Mapping[str, Any],
    *,
    store: DocumentStore | None,
) -> tuple[SourceSpan, ResolutionStatus, DocumentSnapshot | None]:
    """Decode ``range_obj``; return span, resolution status, and target snapshot (R235 / R266).

    Malformed ranges never raise — they map to ``UNRESOLVED`` (R266).
    """
    lsp_range = try_parse_lsp_range(range_obj)
    if lsp_range is None:
        return SourceSpan(0, 0), ResolutionStatus.UNRESOLVED, None
    if canonicalize_document_uri(uri) == canonicalize_document_uri(document.uri):
        return proc.codec.to_internal_span(document, lsp_range), ResolutionStatus.RESOLVED, document
    target: Optional[DocumentSnapshot] = None
    if store is not None:
        target = store.resolve(uri)
    if target is not None:
        return proc.codec.to_internal_span(target, lsp_range), ResolutionStatus.RESOLVED, target
    return SourceSpan(0, 0), ResolutionStatus.UNRESOLVED, None


def _parse_locations(
    proc: LspProcess,
    document: DocumentSnapshot,
    result: Any,
    *,
    store: DocumentStore | None = None,
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
        if not isinstance(range_obj, Mapping):
            continue
        span, status, _target = _span_for_uri(proc, document, uri, range_obj, store=store)
        out.append(SymbolLocation(uri=uri, span=span, resolution_status=status))
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
    span = SourceSpan(0, 0)
    if isinstance(range_obj, Mapping):
        lsp_range = try_parse_lsp_range(range_obj)
        if lsp_range is not None:
            span = proc.codec.to_internal_span(document, lsp_range)
    selection = None
    if isinstance(sel, Mapping):
        lsp_sel = try_parse_lsp_range(sel)
        if lsp_sel is not None:
            selection = proc.codec.to_internal_span(document, lsp_sel)
    children_raw = item.get("children") or ()
    children = tuple(_parse_outline(proc, document, child) for child in children_raw if isinstance(child, Mapping))
    return OutlineSymbol(
        name=name,
        kind=kind,
        span=span,
        selection_span=selection,
        children=children,
    )


def _parse_text_edits(
    proc: LspProcess,
    document: DocumentSnapshot,
    uri: str,
    result: Any,
    *,
    store: DocumentStore | None = None,
    expected_version: int | None = None,
) -> tuple[WorkspaceTextEdit, ...]:
    if not result:
        return ()
    if not isinstance(result, Sequence) or isinstance(result, (str, bytes)):
        return ()
    out: list[WorkspaceTextEdit] = []
    for item in result:
        if not isinstance(item, Mapping):
            continue
        range_obj = item.get("range")
        new_text = item.get("newText")
        if not isinstance(range_obj, Mapping) or new_text is None:
            continue
        span, status, target = _span_for_uri(proc, document, uri, range_obj, store=store)
        version = expected_version
        if version is None and target is not None:
            version = target.version
        out.append(
            WorkspaceTextEdit(
                uri=uri,
                edit=TextEdit(span=span, new_text=str(new_text)),
                expected_version=version,
                resolution_status=status,
            )
        )
    return tuple(out)


def _parse_workspace_edit(
    proc: LspProcess,
    document: DocumentSnapshot,
    result: Any,
    *,
    store: DocumentStore | None = None,
) -> tuple[WorkspaceTextEdit, ...]:
    if not result or not isinstance(result, Mapping):
        return ()
    out: list[WorkspaceTextEdit] = []
    changes = result.get("changes")
    if isinstance(changes, Mapping):
        for uri, edits in changes.items():
            out.extend(_parse_text_edits(proc, document, str(uri), edits, store=store))
    doc_changes = result.get("documentChanges")
    if isinstance(doc_changes, Sequence):
        for change in doc_changes:
            if not isinstance(change, Mapping):
                continue
            if "textDocument" in change and "edits" in change:
                td = change.get("textDocument") or {}
                if not isinstance(td, Mapping):
                    continue
                uri = str(td.get("uri", document.uri))
                raw_ver = td.get("version")
                expected = raw_ver if isinstance(raw_ver, int) else None
                out.extend(
                    _parse_text_edits(
                        proc,
                        document,
                        uri,
                        change.get("edits"),
                        store=store,
                        expected_version=expected,
                    )
                )
    return tuple(out)


def build_rust_semantic_provider(
    registry: LspProcessRegistry,
    workspace_root: str,
    *,
    binary: str,
    allowlist: Iterable[str],
    readiness: SemanticReadiness,
    extra_args: Sequence[str] = (),
    toolchain: str = "",
    document_store: DocumentStore | None = None,
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
    return LspSemanticProvider(registry, config, readiness=readiness, document_store=document_store)


def build_clangd_semantic_provider(
    registry: LspProcessRegistry,
    workspace_root: str,
    *,
    binary: str,
    allowlist: Iterable[str],
    readiness: SemanticReadiness,
    extra_args: Sequence[str] = (),
    toolchain: str = "",
    document_store: DocumentStore | None = None,
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
    return LspSemanticProvider(registry, config, readiness=readiness, document_store=document_store)


__all__ = [
    "LspSemanticConfig",
    "LspSemanticProvider",
    "build_clangd_semantic_provider",
    "build_rust_semantic_provider",
]
