# -*- coding: utf-8 -*-
"""R226: FFI EXACT requires Tree-sitter structural registration proof."""

from __future__ import annotations

import pytest
from core.bindings import (
    BindingEdge,
    BindingEvidence,
    BindingEvidenceKind,
    BindingFramework,
    BindingPrecision,
)
from core.symbol_index import SourceSpan
from infrastructure import ffi_structural
from infrastructure.ffi_bindings import (
    CPythonBindingProvider,
    Pybind11BindingProvider,
    PyO3BindingProvider,
)

tree_sitter = pytest.importorskip("tree_sitter")
pytest.importorskip("tree_sitter_rust")
pytest.importorskip("tree_sitter_cpp")


def test_exact_requires_structural_registration_evidence() -> None:
    """R226: EXACT without STRUCTURAL_REGISTRATION is rejected at the contract."""
    with pytest.raises(ValueError, match="structural_registration|registration"):
        BindingEdge(
            python_symbol="python:_native.x",
            native_symbol="rust:x",
            framework=BindingFramework.PYO3,
            precision=BindingPrecision.EXACT,
            evidence=(
                BindingEvidence(
                    kind=BindingEvidenceKind.PYFUNCTION_ATTR,
                    uri="u",
                    span=SourceSpan(0, 1),
                ),
                BindingEvidence(
                    kind=BindingEvidenceKind.WRAP_PYFUNCTION,
                    uri="u",
                    span=SourceSpan(0, 1),
                ),
                BindingEvidence(
                    kind=BindingEvidenceKind.PYMODULE_ATTR,
                    uri="u",
                    span=SourceSpan(0, 1),
                ),
            ),
        )


def test_r226_pyo3_wrap_outside_pymodule_is_bridge() -> None:
    src = """
#[pyfunction]
fn foo() {}

#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    Ok(())
}

fn other() {
    let _ = wrap_pyfunction!(foo, m);
}
"""
    edges = PyO3BindingProvider().extract("file:///lib.rs", src)
    assert len(edges) == 1
    assert edges[0].precision is BindingPrecision.BRIDGE
    kinds = {e.kind for e in edges[0].evidence}
    assert BindingEvidenceKind.WRAP_PYFUNCTION in kinds
    assert BindingEvidenceKind.STRUCTURAL_REGISTRATION not in kinds


def test_r226_pyo3_happy_path_has_structural() -> None:
    src = """
#[pyfunction]
fn foo() {}

#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(foo, m)?)?;
    Ok(())
}
"""
    edges = PyO3BindingProvider().extract("file:///lib.rs", src)
    assert len(edges) == 1
    assert edges[0].precision is BindingPrecision.EXACT
    assert BindingEvidenceKind.STRUCTURAL_REGISTRATION in {e.kind for e in edges[0].evidence}


def test_r226_pybind11_orphan_def_is_bridge() -> None:
    src = """
PYBIND11_MODULE(_native, m) {
    m.def("inside", &engine::inside);
}
void orphan() {
    m.def("orphan", &engine::orphan);
}
"""
    edges = Pybind11BindingProvider().extract("file:///bindings.cpp", src)
    by_name = {e.python_name: e for e in edges}
    assert by_name["inside"].precision is BindingPrecision.EXACT
    assert BindingEvidenceKind.STRUCTURAL_REGISTRATION in {e.kind for e in by_name["inside"].evidence}
    assert by_name["orphan"].precision is BindingPrecision.BRIDGE
    assert BindingEvidenceKind.STRUCTURAL_REGISTRATION not in {e.kind for e in by_name["orphan"].evidence}


def test_r226_pybind11_shared_binder_stays_in_own_module() -> None:
    src = """
PYBIND11_MODULE(a, m) {
    m.def("a_only", &engine::a);
}
PYBIND11_MODULE(b, m) {
    m.def("b_only", &engine::b);
}
"""
    edges = Pybind11BindingProvider().extract("file:///bindings.cpp", src)
    by_name = {e.python_name: e for e in edges}
    assert by_name["a_only"].python_module == "a"
    assert by_name["a_only"].precision is BindingPrecision.EXACT
    assert by_name["b_only"].python_module == "b"
    assert by_name["b_only"].precision is BindingPrecision.EXACT


def test_r226_cpython_happy_path_has_structural() -> None:
    src = """
static PyMethodDef methods[] = {
    {"solve", py_solve, METH_VARARGS, nullptr},
    {nullptr, nullptr, 0, nullptr},
};
static PyModuleDef module = {
    PyModuleDef_HEAD_INIT,
    .m_name = "_native",
    .m_methods = methods,
};
PyMODINIT_FUNC PyInit__native(void) {
    return PyModule_Create(&module);
}
"""
    edges = CPythonBindingProvider().extract("file:///ext.c", src)
    assert len(edges) == 1
    assert edges[0].precision is BindingPrecision.EXACT
    assert BindingEvidenceKind.STRUCTURAL_REGISTRATION in {e.kind for e in edges[0].evidence}


def test_r226_without_treesitter_never_exact(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail-closed: regex chain alone must not yield EXACT when CST is unavailable."""
    monkeypatch.setattr(ffi_structural, "try_parse_root", lambda *_a, **_k: None)
    src = """
#[pyfunction]
fn foo() {}
#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(foo, m)?)?;
    Ok(())
}
"""
    edges = PyO3BindingProvider().extract("file:///lib.rs", src)
    assert len(edges) == 1
    assert edges[0].precision is BindingPrecision.BRIDGE
