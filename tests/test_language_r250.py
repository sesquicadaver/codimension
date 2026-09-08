# -*- coding: utf-8 -*-
"""R250: pybind11 EXACT requires a real ``.def()`` call_expression."""

from __future__ import annotations

import pytest
from core.bindings import BindingEvidenceKind, BindingPrecision
from infrastructure.ffi_bindings import Pybind11BindingProvider
from infrastructure.ffi_structural import pybind11_registration_proof

tree_sitter = pytest.importorskip("tree_sitter")
pytest.importorskip("tree_sitter_cpp")


def test_r250_commented_def_is_bridge_not_exact() -> None:
    """Regex hit inside MODULE body from a comment must not become EXACT."""
    src = """
PYBIND11_MODULE(_native, m) {
    m.def("real", &engine::real);
    // m.def("unsafe", &engine::unsafe);
}
"""
    edges = Pybind11BindingProvider().extract("file:///bindings.cpp", src)
    by_name = {e.python_name: e for e in edges}
    assert by_name["real"].precision is BindingPrecision.EXACT
    assert BindingEvidenceKind.STRUCTURAL_REGISTRATION in {e.kind for e in by_name["real"].evidence}
    assert by_name["unsafe"].precision is BindingPrecision.BRIDGE
    assert BindingEvidenceKind.STRUCTURAL_REGISTRATION not in {e.kind for e in by_name["unsafe"].evidence}

    assert pybind11_registration_proof(
        src,
        module="_native",
        var="m",
        py_name="unsafe",
        def_start=src.index('m.def("unsafe"'),
        native_name="engine::unsafe",
    ) is None
    proof = pybind11_registration_proof(
        src,
        module="_native",
        var="m",
        py_name="real",
        def_start=src.index('m.def("real"'),
        native_name="engine::real",
    )
    assert proof is not None
    assert proof.registration == "def"
    assert proof.python_name == "real"
    assert proof.native_name == "engine::real"
    assert "call" in proof.detail


def test_r250_string_literal_lookalike_is_bridge() -> None:
    """Block-comment ``.def`` text must not promote to EXACT."""
    src = """
PYBIND11_MODULE(_native, m) {
    m.def("alive", &engine::alive);
    /* m.def("ghost", &engine::ghost); */
}
"""
    edges = Pybind11BindingProvider().extract("file:///bindings.cpp", src)
    by_name = {e.python_name: e for e in edges}
    assert by_name["alive"].precision is BindingPrecision.EXACT
    assert by_name["ghost"].precision is BindingPrecision.BRIDGE


def test_r250_proof_span_is_call_not_whole_module_body() -> None:
    src = """
PYBIND11_MODULE(mod, m) {
    m.def("a", &engine::a);
    m.def("b", &engine::b);
}
"""
    proof = pybind11_registration_proof(
        src,
        module="mod",
        var="m",
        py_name="b",
        def_start=src.index('m.def("b"'),
        native_name="engine::b",
    )
    assert proof is not None
    snippet = src[proof.span.start : proof.span.end]
    assert 'm.def("b"' in snippet
    assert 'm.def("a"' not in snippet
