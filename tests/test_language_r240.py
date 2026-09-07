# -*- coding: utf-8 -*-
"""R240: FFI EXACT requires edge-specific structural registration identity."""

from __future__ import annotations

import pytest
from core.bindings import BindingEvidenceKind, BindingPrecision
from infrastructure.ffi_bindings import (
    CPythonBindingProvider,
    PyO3BindingProvider,
)
from infrastructure.ffi_structural import (
    StructuralRegistrationProof,
    cpython_registration_proof,
    pyo3_registration_proof,
)

tree_sitter = pytest.importorskip("tree_sitter")
pytest.importorskip("tree_sitter_rust")
pytest.importorskip("tree_sitter_cpp")


def test_r240_pyo3_wrap_without_add_function_is_bridge() -> None:
    """Wrap inside #[pymodule] without add_function must not be EXACT."""
    src = """
#[pyfunction]
fn foo() {}

#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    let _ = wrap_pyfunction!(foo, m);
    Ok(())
}
"""
    edges = PyO3BindingProvider().extract("file:///lib.rs", src)
    assert len(edges) == 1
    assert edges[0].precision is BindingPrecision.BRIDGE
    assert BindingEvidenceKind.STRUCTURAL_REGISTRATION not in {e.kind for e in edges[0].evidence}
    assert pyo3_registration_proof(src, "foo") is None


def test_r240_pyo3_module_identity_from_proof_not_first_regex() -> None:
    """EXACT module comes from the pymodule that registers the wrap."""
    src = """
#[pymodule]
fn first(m: &Bound<'_, PyModule>) -> PyResult<()> {
    Ok(())
}

#[pyfunction]
fn foo() {}

#[pymodule]
fn second(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(foo, m)?)?;
    Ok(())
}
"""
    proof = pyo3_registration_proof(src, "foo")
    assert proof is not None
    assert proof.module == "second"
    assert proof.registration == "add_function"
    assert proof.native_name == "foo"

    edges = PyO3BindingProvider().extract("file:///lib.rs", src)
    assert len(edges) == 1
    assert edges[0].precision is BindingPrecision.EXACT
    assert edges[0].python_module == "second"
    assert edges[0].python_symbol == "python:second.foo"


def test_r240_cpython_duplicate_py_name_is_table_specific() -> None:
    """Duplicate export names in two tables must not share the wrong proof."""
    src = """
static PyMethodDef methods_a[] = {
    {"dup", py_a, METH_VARARGS, nullptr},
    {nullptr, nullptr, 0, nullptr},
};
static PyMethodDef methods_b[] = {
    {"dup", py_b, METH_VARARGS, nullptr},
    {nullptr, nullptr, 0, nullptr},
};
static PyModuleDef mod_a = {
    PyModuleDef_HEAD_INIT,
    .m_name = "a",
    .m_methods = methods_a,
};
static PyModuleDef mod_b = {
    PyModuleDef_HEAD_INIT,
    .m_name = "b",
    .m_methods = methods_b,
};
PyMODINIT_FUNC PyInit_a(void) {
    return PyModule_Create(&mod_a);
}
PyMODINIT_FUNC PyInit_b(void) {
    return PyModule_Create(&mod_b);
}
"""
    proof_a = cpython_registration_proof(src, "dup", table_name="methods_a", native_fn="py_a")
    proof_b = cpython_registration_proof(src, "dup", table_name="methods_b", native_fn="py_b")
    assert proof_a is not None and proof_b is not None
    assert proof_a.module == "a"
    assert proof_a.binder == "methods_a"
    assert proof_a.native_name == "py_a"
    assert proof_b.module == "b"
    assert proof_b.binder == "methods_b"
    assert proof_b.native_name == "py_b"
    # Cross-table mismatch must fail closed.
    assert cpython_registration_proof(src, "dup", table_name="methods_a", native_fn="py_b") is None

    edges = CPythonBindingProvider().extract("file:///ext.c", src)
    by_native = {e.native_symbol: e for e in edges}
    assert by_native["cpp:py_a"].precision is BindingPrecision.EXACT
    assert by_native["cpp:py_a"].python_module == "a"
    assert by_native["cpp:py_b"].precision is BindingPrecision.EXACT
    assert by_native["cpp:py_b"].python_module == "b"
    assert by_native["cpp:py_a"].evidence[-1].detail != by_native["cpp:py_b"].evidence[-1].detail


def test_r240_proof_carries_identity_fields() -> None:
    """StructuralRegistrationProof documents the full registration chain."""
    proof = StructuralRegistrationProof(
        span=__import__("core.symbol_index", fromlist=["SourceSpan"]).SourceSpan(0, 1),
        detail="x",
        module="m",
        binder="t",
        python_name="p",
        native_name="n",
        registration="add_function",
    )
    assert proof.module == "m"
    assert proof.registration == "add_function"
