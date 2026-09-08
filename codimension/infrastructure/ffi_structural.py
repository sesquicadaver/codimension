# -*- coding: utf-8 -*-
#
# codimension - FFI structural registration proofs (R226 / R240 / R250)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Tree-sitter CST proofs for FFI registration chains (R226 / R240 / R250).

Regex/text discovery (R206/R217) still finds candidates. ``EXACT`` precision
requires a **structural** containment proof from this module that carries
**edge-specific identity** (R240):

* module / init function
* binder or method table
* Python export name (when known from CST)
* native function
* concrete registration call
* source span of the registration site

Framework rules:

* PyO3 — ``wrap_pyfunction!(fn, …)`` is an argument of ``*.add_function(…)``
  inside a ``#[pymodule]`` function body (not merely co-located).
* pybind11 — a real ``call_expression`` ``var.def("name", &native)`` inside the
  matching ``PYBIND11_MODULE(mod, var)`` body (R250: offset-in-body alone is
  not enough; comments / string literals must not promote to ``EXACT``).
* CPython — ``PyMethodDef`` row for a **specific** method table ↔ that table
  on ``PyModuleDef.m_methods`` ↔ ``PyInit_*`` / ``PyModule_Create``.

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
    """Located CST proof with full registration-chain identity (R240)."""

    span: SourceSpan
    detail: str
    module: str = ""
    binder: str = ""
    python_name: str = ""
    native_name: str = ""
    registration: str = ""


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


def _function_item_name(source_bytes: bytes, function_item: Any) -> str:
    """Return the identifier name of a Rust ``function_item``."""
    name = function_item.child_by_field_name("name")
    if name is not None:
        return _node_text(source_bytes, name)
    for child in function_item.children:
        if child.type == "identifier":
            return _node_text(source_bytes, child)
    return ""


def _is_pymodule_function(source_bytes: bytes, function_item: Any) -> bool:
    """True when ``function_item`` has a directly preceding ``#[pymodule]``."""
    parent = function_item.parent
    if parent is None:
        return False
    for sib in _leading_rust_attrs(parent, function_item):
        if "pymodule" in _attr_names(source_bytes, sib):
            return True
    return False


def _call_callee_name(source_bytes: bytes, call_node: Any) -> str:
    """Return the method/function name of a Rust ``call_expression``."""
    if not call_node.children:
        return ""
    head = call_node.children[0]
    if head.type == "field_expression":
        for child in reversed(list(head.children)):
            if child.type in {"field_identifier", "identifier"}:
                return _node_text(source_bytes, child)
        return ""
    if head.type == "identifier":
        return _node_text(source_bytes, head)
    return ""


def _ancestor_add_function_call(source_bytes: bytes, node: Any) -> Any | None:
    """Nearest ancestor ``call_expression`` whose callee is ``add_function``."""
    parent = node.parent
    while parent is not None:
        if parent.type == "call_expression" and _call_callee_name(source_bytes, parent) == "add_function":
            return parent
        parent = parent.parent
    return None


def _enclosing_function_item(node: Any) -> Any | None:
    """Nearest ancestor ``function_item``."""
    parent = node.parent
    while parent is not None:
        if parent.type == "function_item":
            return parent
        parent = parent.parent
    return None


def pyo3_registration_proof(text: str, rust_fn: str) -> Optional[StructuralRegistrationProof]:
    """Prove ``add_function(wrap_pyfunction!(rust_fn, …))`` inside a ``#[pymodule]``.

    R240: wrap alone inside a pymodule body is insufficient — the wrap must be
    an argument of a concrete ``add_function`` registration call, and the
    enclosing pymodule function name becomes the proof's module identity.
    """
    root = try_parse_root("rust", text)
    if root is None:
        return None
    source_bytes = text.encode("utf-8")
    target = rust_fn.strip()
    if not target:
        return None

    for node in _walk(root):
        if node.type != "macro_invocation":
            continue
        macro_name = None
        for child in node.children:
            if child.type == "identifier":
                macro_name = _node_text(source_bytes, child)
                break
        if macro_name != "wrap_pyfunction":
            continue
        matched = False
        for child in node.children:
            if child.type != "token_tree":
                continue
            idents = [c for c in child.children if c.type == "identifier"]
            if idents and _node_text(source_bytes, idents[0]) == target:
                matched = True
                break
        if not matched:
            continue
        add_call = _ancestor_add_function_call(source_bytes, node)
        if add_call is None:
            continue
        fn_item = _enclosing_function_item(add_call)
        if fn_item is None or not _is_pymodule_function(source_bytes, fn_item):
            continue
        module = _function_item_name(source_bytes, fn_item)
        if not module:
            continue
        span = unicode_span_from_bytes(text, add_call.start_byte, add_call.end_byte)
        return StructuralRegistrationProof(
            span=span,
            detail=(f"add_function(wrap_pyfunction!({target})) inside #[pymodule] fn {module}"),
            module=module,
            binder=module,
            python_name="",
            native_name=target,
            registration="add_function",
        )
    return None


def _pybind11_module_entries(text: str) -> tuple[tuple[str, str, Any, SourceSpan], ...]:
    """Return ``(module, var, body_node, body_span)`` for each ``PYBIND11_MODULE``."""
    root = try_parse_root("cpp", text)
    if root is None:
        return ()
    source_bytes = text.encode("utf-8")
    out: list[tuple[str, str, Any, SourceSpan]] = []
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
        out.append((module, var, body, span))
    return tuple(out)


def pybind11_module_bodies(text: str) -> tuple[tuple[str, str, SourceSpan], ...]:
    """Return ``(module, var, body_span)`` for each ``PYBIND11_MODULE`` CST node."""
    return tuple((module, var, span) for module, var, _body, span in _pybind11_module_entries(text))


def _pybind11_string_literal_content(source_bytes: bytes, node: Any) -> str | None:
    """Return decoded content of a C++ ``string_literal`` node, or ``None``."""
    if node.type != "string_literal":
        return None
    content = next((c for c in node.children if c.type == "string_content"), None)
    if content is None:
        return None
    return _node_text(source_bytes, content)


def _pybind11_native_arg_name(source_bytes: bytes, arg: Any) -> str:
    """Best-effort native symbol text from a ``.def`` second argument."""
    if arg.type == "identifier":
        return _node_text(source_bytes, arg)
    # Prefer fully-qualified names (&engine::fn → engine::fn).
    for child in _walk(arg):
        if child.type == "qualified_identifier":
            return _node_text(source_bytes, child)
    for child in _walk(arg):
        if child.type == "identifier":
            return _node_text(source_bytes, child)
    return ""


def _pybind11_def_call_identity(
    source_bytes: bytes, call_node: Any
) -> tuple[str, str, str] | None:
    """Parse ``binder.def("py_name", native…)`` → ``(binder, py_name, native)``."""
    if call_node.type != "call_expression" or len(call_node.children) < 2:
        return None
    head = call_node.children[0]
    args = next((c for c in call_node.children if c.type == "argument_list"), None)
    if head.type != "field_expression" or args is None:
        return None
    binder = None
    method = None
    for child in head.children:
        if child.type == "identifier" and binder is None:
            binder = _node_text(source_bytes, child)
        elif child.type == "field_identifier":
            method = _node_text(source_bytes, child)
    if not binder or method != "def":
        return None
    named_args = [c for c in args.children if c.is_named]
    if len(named_args) < 2:
        return None
    py_name = _pybind11_string_literal_content(source_bytes, named_args[0])
    if not py_name:
        return None
    native = _pybind11_native_arg_name(source_bytes, named_args[1])
    return binder, py_name, native


def pybind11_registration_proof(
    text: str,
    *,
    module: str,
    var: str,
    py_name: str,
    def_start: int,
    native_name: str = "",
) -> Optional[StructuralRegistrationProof]:
    """Prove a concrete ``var.def("py_name", …)`` ``call_expression`` (R250).

    Regex may nominate ``def_start`` / names, but ``EXACT`` identity comes only
    from a Tree-sitter ``call_expression`` whose binder, export string, and
    native argument match inside the matching ``PYBIND11_MODULE`` body.
    """
    want_py = py_name.strip()
    want_native = native_name.strip()
    if not want_py:
        return None
    source_bytes = text.encode("utf-8")
    best: StructuralRegistrationProof | None = None
    for mod_name, binder, body, _body_span in _pybind11_module_entries(text):
        if mod_name != module or binder != var:
            continue
        for node in _walk(body):
            if node.type != "call_expression":
                continue
            parts = _pybind11_def_call_identity(source_bytes, node)
            if parts is None:
                continue
            call_binder, call_py, call_native = parts
            if call_binder != var or call_py != want_py:
                continue
            if want_native and call_native and call_native != want_native:
                continue
            native_resolved = call_native or want_native
            span = unicode_span_from_bytes(text, node.start_byte, node.end_byte)
            candidate = StructuralRegistrationProof(
                span=span,
                detail=(
                    f"PYBIND11_MODULE({mod_name}, {binder}) "
                    f'call {binder}.def("{call_py}", &{native_resolved})'
                ),
                module=mod_name,
                binder=binder,
                python_name=call_py,
                native_name=native_resolved,
                registration="def",
            )
            # Prefer the call that covers the regex offset when several match.
            if node.start_byte <= def_start < node.end_byte:
                return candidate
            if best is None:
                best = candidate
    return best


def cpython_registration_proof(
    text: str,
    py_name: str | None = None,
    *,
    table_name: str = "",
    native_fn: str = "",
) -> Optional[StructuralRegistrationProof]:
    """Prove a MethodDef row is linked via ``m_methods`` + ``PyModule_Create``.

    R240: callers must pass the candidate ``table_name`` (and preferably
    ``native_fn``) so duplicate ``py_name`` rows in other tables cannot
    satisfy the proof. Positional ``py_name`` is retained for R226 callers.
    """
    target = (py_name or "").strip()
    table_want = table_name.strip()
    native_want = native_fn.strip()
    if not target or not table_want:
        return None
    root = try_parse_root("cpp", text)
    if root is None:
        return None
    source_bytes = text.encode("utf-8")

    # table_name → list of (py_name, native_fn, row_span)
    tables: dict[str, list[tuple[str, str, SourceSpan]]] = {}
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
        found_table = None
        for child in init.children:
            if child.type == "array_declarator":
                ident = next((c for c in child.children if c.type == "identifier"), None)
                if ident is not None:
                    found_table = _node_text(source_bytes, ident)
            elif child.type == "identifier" and found_table is None:
                found_table = _node_text(source_bytes, child)
        if not found_table:
            continue
        rows: list[tuple[str, str, SourceSpan]] = []
        for child in _walk(init):
            if child.type != "initializer_list":
                continue
            # Row-level lists contain a string_literal as first named content.
            for row in child.children:
                if row.type != "initializer_list":
                    continue
                named = [c for c in row.children if c.is_named]
                if len(named) < 2:
                    continue
                first = named[0]
                if first.type != "string_literal":
                    continue
                content = next((c for c in first.children if c.type == "string_content"), None)
                if content is None:
                    continue
                name = _node_text(source_bytes, content)
                native_node = named[1]
                native = ""
                if native_node.type == "identifier":
                    native = _node_text(source_bytes, native_node)
                else:
                    ident = next((c for c in _walk(native_node) if c.type == "identifier"), None)
                    if ident is not None:
                        native = _node_text(source_bytes, ident)
                rows.append(
                    (
                        name,
                        native,
                        unicode_span_from_bytes(text, row.start_byte, row.end_byte),
                    )
                )
        if rows:
            tables.setdefault(found_table, []).extend(rows)

    if table_want not in tables:
        return None
    row_hit = None
    for name, native, row_span in tables[table_want]:
        if name != target:
            continue
        if native_want and native and native != native_want:
            continue
        row_hit = (name, native or native_want, row_span)
        break
    if row_hit is None:
        return None
    _py, native_resolved, _row_span = row_hit

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

    # PyInit_* containing PyModule_Create(&def) for the wanted table only.
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
            if def_ref is None or def_to_table.get(def_ref) != table_want:
                continue
            module = fn_name[len("PyInit_") :]
            span = unicode_span_from_bytes(text, descendant.start_byte, descendant.end_byte)
            return StructuralRegistrationProof(
                span=span,
                detail=(
                    f'PyMethodDef "{target}"/{native_resolved} via {table_want} → '
                    f"{def_ref}.m_methods → {fn_name}/PyModule_Create"
                ),
                module=module,
                binder=table_want,
                python_name=target,
                native_name=native_resolved,
                registration="PyModule_Create",
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
