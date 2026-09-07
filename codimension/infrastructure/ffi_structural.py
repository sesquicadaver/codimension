# -*- coding: utf-8 -*-
#
# codimension - FFI structural registration proofs (R226)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Tree-sitter CST proofs for FFI registration chains (R226).

Regex/text discovery (R206/R217) still finds candidates. ``EXACT`` precision
requires a **structural** containment proof from this module:

* PyO3 — ``wrap_pyfunction!(fn, …)`` is a descendant of a ``#[pymodule]``
  function body (attribute is a preceding sibling of ``function_item``).
* pybind11 — ``var.def("name", …)`` lies inside the ``compound_statement`` of
  the matching ``PYBIND11_MODULE(mod, var)``.
* CPython — ``PyMethodDef`` row ↔ ``PyModuleDef.m_methods`` ↔
  ``PyInit_*`` / ``PyModule_Create`` via AST fields (no char windows).

When Tree-sitter / grammars are unavailable, proofs return ``None`` and
extractors must emit ``BRIDGE`` (fail-closed).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from core.symbol_index import SourceSpan
from infrastructure.tree_sitter_structural import (
    TreeSitterUnavailableError,
    load_tree_sitter_language,
    unicode_span_from_bytes,
)


@dataclass(frozen=True, slots=True)
class StructuralRegistrationProof:
    """Located CST proof that a registration chain is structurally valid."""

    span: SourceSpan
    detail: str


def try_parse_root(language_id: str, text: str) -> Any | None:
    """Parse ``text`` with Tree-sitter; return root node or ``None``."""
    try:
        from tree_sitter import Parser
    except ImportError:
        return None
    try:
        language = load_tree_sitter_language(language_id)
    except (TreeSitterUnavailableError, ValueError):
        return None
    source_bytes = text.encode("utf-8")
    try:
        tree = Parser(language).parse(source_bytes)
    except Exception:
        return None
    return tree.root_node


def _node_text(source_bytes: bytes, node: Any) -> str:
    return source_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _walk(node: Any):
    """Yield ``node`` then descendants (pre-order)."""
    yield node
    for child in node.children:
        yield from _walk(child)


def _attr_names(source_bytes: bytes, attr_item: Any) -> set[str]:
    """Extract identifier names from a Rust ``attribute_item``."""
    names: set[str] = set()
    for child in _walk(attr_item):
        if child.type == "identifier":
            names.add(_node_text(source_bytes, child))
    return names


def _leading_rust_attrs(parent: Any, function_item: Any) -> list[Any]:
    """Return consecutive ``attribute_item`` nodes immediately before ``function_item``.

    Rust attributes apply only when they directly precede the item; walking all
    earlier siblings would incorrectly attach a prior ``#[pymodule]`` to a later
    unrelated function (R226).
    """
    siblings = list(parent.children)
    try:
        idx = siblings.index(function_item)
    except ValueError:
        return []
    attrs: list[Any] = []
    i = idx - 1
    while i >= 0:
        sib = siblings[i]
        if not sib.is_named:
            i -= 1
            continue
        if sib.type == "attribute_item":
            attrs.append(sib)
            i -= 1
            continue
        break
    attrs.reverse()
    return attrs


def pyo3_registration_proof(text: str, rust_fn: str) -> Optional[StructuralRegistrationProof]:
    """Prove ``wrap_pyfunction!(rust_fn, …)`` sits inside a ``#[pymodule]`` body."""
    root = try_parse_root("rust", text)
    if root is None:
        return None
    source_bytes = text.encode("utf-8")
    target = rust_fn.strip()
    if not target:
        return None

    for node in _walk(root):
        if node.type != "function_item":
            continue
        parent = node.parent
        if parent is None:
            continue
        has_pymodule = False
        for sib in _leading_rust_attrs(parent, node):
            names = _attr_names(source_bytes, sib)
            if "pymodule" in names:
                has_pymodule = True
                break
        if not has_pymodule:
            continue
        body = node.child_by_field_name("body")
        if body is None:
            continue
        for descendant in _walk(body):
            if descendant.type != "macro_invocation":
                continue
            # First child identifier is the macro name.
            macro_name = None
            for child in descendant.children:
                if child.type == "identifier":
                    macro_name = _node_text(source_bytes, child)
                    break
            if macro_name != "wrap_pyfunction":
                continue
            # First identifier inside token_tree is the rust fn.
            for child in descendant.children:
                if child.type != "token_tree":
                    continue
                idents = [c for c in child.children if c.type == "identifier"]
                if idents and _node_text(source_bytes, idents[0]) == target:
                    span = unicode_span_from_bytes(text, descendant.start_byte, descendant.end_byte)
                    return StructuralRegistrationProof(
                        span=span,
                        detail=f"wrap_pyfunction!({target}) inside #[pymodule] body",
                    )
    return None


def pybind11_module_bodies(text: str) -> tuple[tuple[str, str, SourceSpan], ...]:
    """Return ``(module, var, body_span)`` for each ``PYBIND11_MODULE`` CST node."""
    root = try_parse_root("cpp", text)
    if root is None:
        return ()
    source_bytes = text.encode("utf-8")
    out: list[tuple[str, str, SourceSpan]] = []
    for node in _walk(root):
        if node.type != "function_definition":
            continue
        declarator = None
        body = None
        for child in node.children:
            if child.type == "function_declarator":
                declarator = child
            elif child.type == "compound_statement":
                body = child
        if declarator is None or body is None:
            continue
        name_node = None
        params = None
        for child in declarator.children:
            if child.type == "identifier" and name_node is None:
                name_node = child
            elif child.type == "parameter_list":
                params = child
        if name_node is None or params is None:
            continue
        if _node_text(source_bytes, name_node) != "PYBIND11_MODULE":
            continue
        # Parameters are typically type_identifier / identifier leaves.
        param_ids: list[str] = []
        for child in params.children:
            if not child.is_named:
                continue
            # parameter_declaration → type_identifier or identifier
            leaf = None
            for sub in _walk(child):
                if sub.type in {"type_identifier", "identifier", "field_identifier"}:
                    leaf = sub
                    break
            if leaf is not None:
                param_ids.append(_node_text(source_bytes, leaf))
        if len(param_ids) < 2:
            continue
        module, var = param_ids[0], param_ids[1]
        span = unicode_span_from_bytes(text, body.start_byte, body.end_byte)
        out.append((module, var, span))
    return tuple(out)


def pybind11_registration_proof(
    text: str,
    *,
    module: str,
    var: str,
    py_name: str,
    def_start: int,
) -> Optional[StructuralRegistrationProof]:
    """Prove ``var.def("py_name", …)`` at ``def_start`` is inside that MODULE body."""
    for mod_name, binder, body_span in pybind11_module_bodies(text):
        if mod_name != module or binder != var:
            continue
        if body_span.start <= def_start < body_span.end:
            return StructuralRegistrationProof(
                span=body_span,
                detail=f'PYBIND11_MODULE({module}, {var}) contains .def("{py_name}")',
            )
    return None


def cpython_registration_proof(text: str, py_name: str) -> Optional[StructuralRegistrationProof]:
    """Prove MethodDef row ``py_name`` is linked via ``m_methods`` + ``PyModule_Create``.

    Returns a proof spanning the ``PyModule_Create`` call when the full chain
    is present in the CST.
    """
    root = try_parse_root("cpp", text)
    if root is None:
        return None
    source_bytes = text.encode("utf-8")
    target = py_name.strip()
    if not target:
        return None

    # table_name → list of (py_name, row_span)
    tables: dict[str, list[tuple[str, SourceSpan]]] = {}
    for node in _walk(root):
        if node.type != "declaration":
            continue
        # Look for PyMethodDef … table[] = { … }
        type_ids = [c for c in node.children if c.type == "type_identifier"]
        if not type_ids or _node_text(source_bytes, type_ids[0]) != "PyMethodDef":
            continue
        init = next((c for c in node.children if c.type == "init_declarator"), None)
        if init is None:
            continue
        table_name = None
        for child in init.children:
            if child.type == "array_declarator":
                ident = next((c for c in child.children if c.type == "identifier"), None)
                if ident is not None:
                    table_name = _node_text(source_bytes, ident)
            elif child.type == "identifier" and table_name is None:
                table_name = _node_text(source_bytes, child)
        if not table_name:
            continue
        rows: list[tuple[str, SourceSpan]] = []
        for child in _walk(init):
            if child.type != "initializer_list":
                continue
            # Row-level lists contain a string_literal as first named content.
            for row in child.children:
                if row.type != "initializer_list":
                    continue
                named = [c for c in row.children if c.is_named]
                if not named:
                    continue
                first = named[0]
                if first.type != "string_literal":
                    continue
                content = next((c for c in first.children if c.type == "string_content"), None)
                if content is None:
                    continue
                name = _node_text(source_bytes, content)
                rows.append(
                    (
                        name,
                        unicode_span_from_bytes(text, row.start_byte, row.end_byte),
                    )
                )
        if rows:
            tables.setdefault(table_name, []).extend(rows)

    # def_name → table_name from .m_methods
    def_to_table: dict[str, str] = {}
    for node in _walk(root):
        if node.type != "declaration":
            continue
        type_ids = [c for c in node.children if c.type == "type_identifier"]
        if not type_ids or _node_text(source_bytes, type_ids[0]) != "PyModuleDef":
            continue
        init = next((c for c in node.children if c.type == "init_declarator"), None)
        if init is None:
            continue
        def_name = None
        for child in init.children:
            if child.type == "identifier":
                def_name = _node_text(source_bytes, child)
                break
        if not def_name:
            continue
        for child in _walk(init):
            if child.type != "initializer_pair":
                continue
            designator = next((c for c in child.children if c.type == "field_designator"), None)
            if designator is None:
                continue
            field = next((c for c in designator.children if c.type == "field_identifier"), None)
            if field is None or _node_text(source_bytes, field) != "m_methods":
                continue
            value = None
            seen_eq = False
            for part in child.children:
                if part.type == "=":
                    seen_eq = True
                    continue
                if seen_eq and part.is_named:
                    value = part
                    break
            if value is not None and value.type == "identifier":
                def_to_table[def_name] = _node_text(source_bytes, value)

    # PyInit_* containing PyModule_Create(&def)
    for node in _walk(root):
        if node.type != "function_definition":
            continue
        declarator = next((c for c in node.children if c.type == "function_declarator"), None)
        body = next((c for c in node.children if c.type == "compound_statement"), None)
        if declarator is None or body is None:
            continue
        fn_ident = next((c for c in declarator.children if c.type == "identifier"), None)
        if fn_ident is None:
            continue
        fn_name = _node_text(source_bytes, fn_ident)
        if not fn_name.startswith("PyInit_"):
            continue
        for descendant in _walk(body):
            if descendant.type != "call_expression":
                continue
            callee = descendant.children[0] if descendant.children else None
            if callee is None or callee.type != "identifier":
                continue
            if _node_text(source_bytes, callee) != "PyModule_Create":
                continue
            args = next((c for c in descendant.children if c.type == "argument_list"), None)
            if args is None:
                continue
            def_ref = None
            for arg in args.children:
                if arg.type == "pointer_expression":
                    ident = next((c for c in arg.children if c.type == "identifier"), None)
                    if ident is not None:
                        def_ref = _node_text(source_bytes, ident)
                elif arg.type == "identifier":
                    def_ref = _node_text(source_bytes, arg)
            if def_ref is None or def_ref not in def_to_table:
                continue
            table = def_to_table[def_ref]
            for name, _row in tables.get(table, []):
                if name == target:
                    span = unicode_span_from_bytes(text, descendant.start_byte, descendant.end_byte)
                    return StructuralRegistrationProof(
                        span=span,
                        detail=(
                            f'PyMethodDef "{target}" via {table} → {def_ref}.m_methods → {fn_name}/PyModule_Create'
                        ),
                    )
    return None


__all__ = [
    "StructuralRegistrationProof",
    "cpython_registration_proof",
    "pybind11_module_bodies",
    "pybind11_registration_proof",
    "pyo3_registration_proof",
    "try_parse_root",
]
