# -*- coding: utf-8 -*-
#
# codimension - Tree-sitter structural provider (R205)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Tree-sitter → :class:`~core.structural.StructuralGraph` (R205).

Pure syntax structure with ``semantic_role`` mapping. This is **not** a
compiler CFG. Tree-sitter packages are optional at install time; when missing,
:func:`build_tree_sitter_structural_provider` raises
:class:`TreeSitterUnavailableError`.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from core.document_snapshot import DocumentSnapshot
from core.structural import (
    SemanticRole,
    StructuralEdge,
    StructuralEdgeKind,
    StructuralGraph,
    StructuralNode,
    StructuralProvider,
)
from core.symbol_index import SourceSpan

#: Rust grammar ``type`` → shared semantic role.
RUST_NODE_ROLES: Mapping[str, SemanticRole] = {
    "source_file": SemanticRole.MODULE,
    "mod_item": SemanticRole.NAMESPACE,
    "use_declaration": SemanticRole.IMPORT,
    "struct_item": SemanticRole.TYPE,
    "enum_item": SemanticRole.TYPE,
    "union_item": SemanticRole.TYPE,
    "type_item": SemanticRole.TYPE,
    "trait_item": SemanticRole.TRAIT,
    "impl_item": SemanticRole.IMPL,
    "function_item": SemanticRole.FUNCTION,
    "closure_expression": SemanticRole.CLOSURE,
    "if_expression": SemanticRole.BRANCH,
    "match_expression": SemanticRole.BRANCH,
    "loop_expression": SemanticRole.LOOP,
    "while_expression": SemanticRole.LOOP,
    "for_expression": SemanticRole.LOOP,
    "return_expression": SemanticRole.RETURN,
    "break_expression": SemanticRole.BREAK,
    "continue_expression": SemanticRole.CONTINUE,
    "try_expression": SemanticRole.EARLY_EXIT,
    "unsafe_block": SemanticRole.UNSAFE,
    "await_expression": SemanticRole.AWAIT,
    "macro_invocation": SemanticRole.MACRO,
    "macro_definition": SemanticRole.MACRO,
}

#: C++ grammar ``type`` → shared semantic role.
CPP_NODE_ROLES: Mapping[str, SemanticRole] = {
    "translation_unit": SemanticRole.MODULE,
    "namespace_definition": SemanticRole.NAMESPACE,
    "preproc_include": SemanticRole.IMPORT,
    "class_specifier": SemanticRole.TYPE,
    "struct_specifier": SemanticRole.TYPE,
    "union_specifier": SemanticRole.TYPE,
    "enum_specifier": SemanticRole.TYPE,
    "alias_declaration": SemanticRole.TYPE,
    "function_definition": SemanticRole.FUNCTION,
    "lambda_expression": SemanticRole.CLOSURE,
    "if_statement": SemanticRole.BRANCH,
    "switch_statement": SemanticRole.BRANCH,
    "while_statement": SemanticRole.LOOP,
    "for_statement": SemanticRole.LOOP,
    "for_range_loop": SemanticRole.LOOP,
    "do_statement": SemanticRole.LOOP,
    "return_statement": SemanticRole.RETURN,
    "break_statement": SemanticRole.BREAK,
    "continue_statement": SemanticRole.CONTINUE,
    "throw_statement": SemanticRole.EXCEPTION_EXIT,
    "try_statement": SemanticRole.BLOCK,
    "preproc_function_def": SemanticRole.MACRO,
    "preproc_def": SemanticRole.MACRO,
}

_ROLE_TABLES: Mapping[str, Mapping[str, SemanticRole]] = {
    "rust": RUST_NODE_ROLES,
    "cpp": CPP_NODE_ROLES,
}

_PYO3_MARKERS = frozenset({"pyfunction", "pymodule", "pyclass", "pyo3"})


class TreeSitterUnavailableError(RuntimeError):
    """Raised when tree-sitter or a language grammar cannot be loaded."""


def utf8_byte_to_unicode_offset(text: str, byte_offset: int) -> int:
    """Map a UTF-8 byte offset into a Unicode character index."""
    if byte_offset <= 0:
        return 0
    raw = text.encode("utf-8")
    if byte_offset >= len(raw):
        return len(text)
    return len(raw[:byte_offset].decode("utf-8"))


def unicode_span_from_bytes(text: str, start_byte: int, end_byte: int) -> SourceSpan:
    """Build a half-open Unicode :class:`SourceSpan` from UTF-8 byte offsets."""
    start = utf8_byte_to_unicode_offset(text, start_byte)
    end = utf8_byte_to_unicode_offset(text, end_byte)
    if end < start:
        end = start
    return SourceSpan(start, end)


def load_tree_sitter_language(language_id: str) -> Any:
    """Return a ``tree_sitter.Language`` for ``language_id`` (``rust`` / ``cpp``)."""
    try:
        from tree_sitter import Language
    except ImportError as exc:  # pragma: no cover - optional dep
        raise TreeSitterUnavailableError("tree-sitter is not installed; pip install 'codimension[treesitter]'") from exc

    lid = language_id.strip().lower()
    try:
        if lid == "rust":
            import tree_sitter_rust as ts_rust

            return Language(ts_rust.language())
        if lid == "cpp":
            import tree_sitter_cpp as ts_cpp

            return Language(ts_cpp.language())
    except ImportError as exc:  # pragma: no cover - optional dep
        raise TreeSitterUnavailableError(
            f"tree-sitter grammar for {lid!r} is not installed; pip install 'codimension[treesitter]'"
        ) from exc
    raise TreeSitterUnavailableError(f"unsupported structural language_id: {language_id!r}")


def role_for_native_kind(language_id: str, native_kind: str) -> SemanticRole | None:
    """Return mapped :class:`SemanticRole` or ``None`` when the node is skipped."""
    table = _ROLE_TABLES.get(language_id.strip().lower())
    if table is None:
        return None
    return table.get(native_kind)


class TreeSitterStructuralProvider:
    """Build :class:`StructuralGraph` from Tree-sitter for one language."""

    def __init__(self, language_id: str, *, language: Any | None = None) -> None:
        """Bind ``language_id``; load grammar when ``language`` is omitted."""
        lid = language_id.strip().lower()
        if lid not in _ROLE_TABLES:
            raise ValueError(f"unsupported structural language_id: {language_id!r}")
        self._language_id = lid
        self._language = language if language is not None else load_tree_sitter_language(lid)
        self._provider_id = f"tree-sitter.{lid}"

    @property
    def provider_id(self) -> str:
        """Stable provider id."""
        return self._provider_id

    @property
    def language_id(self) -> str:
        """Language id this provider builds graphs for."""
        return self._language_id

    def build_graph(self, document: DocumentSnapshot) -> StructuralGraph:
        """Parse ``document.text`` and emit containment structural nodes."""
        from tree_sitter import Parser

        source = document.text
        source_bytes = source.encode("utf-8")
        parser = Parser(self._language)
        tree = parser.parse(source_bytes)
        graph = StructuralGraph(language_id=self._language_id)
        seq = 0
        roles = _ROLE_TABLES[self._language_id]

        def new_id(kind: str) -> str:
            nonlocal seq
            seq += 1
            return f"{kind}_{seq}"

        def label_of(node: Any) -> str:
            name = node.child_by_field_name("name")
            if name is not None:
                raw = source_bytes[name.start_byte : name.end_byte]
                label: str = raw.decode("utf-8", errors="replace")
                return label
            return ""

        def resolve_role(node: Any) -> SemanticRole | None:
            """Map a CST node to a role, or ``None`` to skip emission."""
            if not node.is_named:
                return None
            if self._language_id == "rust" and node.type == "attribute_item":
                chunk = source_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace").lower()
                if any(marker in chunk for marker in _PYO3_MARKERS):
                    return SemanticRole.FFI_BOUNDARY
                return None
            return roles.get(node.type)

        def walk(node: Any, parent_struct_id: str | None) -> None:
            role = resolve_role(node)
            current_parent = parent_struct_id
            if role is not None:
                node_id = new_id(node.type)
                span = unicode_span_from_bytes(source, node.start_byte, node.end_byte)
                graph.nodes[node_id] = StructuralNode(
                    id=node_id,
                    native_kind=node.type,
                    semantic_role=role,
                    span=span,
                    label=label_of(node),
                    parent_id=parent_struct_id,
                )
                if parent_struct_id is None:
                    graph.root_id = node_id
                else:
                    graph.edges.append(
                        StructuralEdge(
                            src=parent_struct_id,
                            dst=node_id,
                            kind=StructuralEdgeKind.CONTAINS,
                        )
                    )
                current_parent = node_id
            for child in node.children:
                walk(child, current_parent)

        walk(tree.root_node, None)
        if not graph.root_id and graph.nodes:
            graph.root_id = next(iter(graph.nodes))
        return graph


def build_tree_sitter_structural_provider(language_id: str) -> StructuralProvider:
    """Construct a Tree-sitter structural provider for ``language_id``."""
    return TreeSitterStructuralProvider(language_id)


def try_build_tree_sitter_structural_provider(
    language_id: str,
) -> Optional[StructuralProvider]:
    """Return a provider or ``None`` when Tree-sitter / grammar is unavailable."""
    try:
        return build_tree_sitter_structural_provider(language_id)
    except (TreeSitterUnavailableError, ValueError):
        return None


__all__ = [
    "CPP_NODE_ROLES",
    "RUST_NODE_ROLES",
    "TreeSitterStructuralProvider",
    "TreeSitterUnavailableError",
    "build_tree_sitter_structural_provider",
    "load_tree_sitter_language",
    "role_for_native_kind",
    "try_build_tree_sitter_structural_provider",
    "unicode_span_from_bytes",
    "utf8_byte_to_unicode_offset",
]
