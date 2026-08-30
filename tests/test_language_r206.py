# -*- coding: utf-8 -*-
"""R206: BindingIndex + PyO3 / pybind11 / CPython / .pyi evidence-backed edges."""

from __future__ import annotations

import pytest
from core.bindings import (
    BindingEdge,
    BindingEvidence,
    BindingEvidenceKind,
    BindingFramework,
    BindingIndex,
    BindingPrecision,
    ExactBindingWithoutEvidenceError,
)
from core.language import LanguageCapability, make_cpp_language_service, make_rust_language_service
from core.symbol_index import SourceSpan
from infrastructure.ffi_bindings import (
    CPythonBindingProvider,
    Pybind11BindingProvider,
    PyiBridgeProvider,
    PyO3BindingProvider,
)


def test_reject_name_only_exact_edge() -> None:
    index = BindingIndex()
    with pytest.raises(ExactBindingWithoutEvidenceError):
        index.reject_name_only_exact(
            python_symbol="python:_native.solve",
            native_symbol="rust:solve",
            framework=BindingFramework.PYO3,
        )
    with pytest.raises(ValueError):
        BindingEdge(
            python_symbol="python:_native.x",
            native_symbol="rust:x",
            framework=BindingFramework.PYO3,
            precision=BindingPrecision.EXACT,
            evidence=(),
        )


def test_pyo3_extractor_with_rename_and_wrap() -> None:
    src = """
use pyo3::prelude::*;

#[pyfunction]
#[pyo3(name = "fast_sum")]
fn fast_sum_impl(a: i64, b: i64) -> i64 {
    a + b
}

#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(fast_sum_impl, m)?)?;
    Ok(())
}
"""
    edges = PyO3BindingProvider().extract("file:///lib.rs", src)
    assert len(edges) == 1
    edge = edges[0]
    assert edge.python_symbol == "python:_native.fast_sum"
    assert edge.native_symbol == "rust:fast_sum_impl"
    assert edge.precision is BindingPrecision.EXACT
    assert edge.framework is BindingFramework.PYO3
    kinds = {e.kind for e in edge.evidence}
    assert BindingEvidenceKind.PYFUNCTION_ATTR in kinds
    assert BindingEvidenceKind.PYO3_NAME_ATTR in kinds
    assert BindingEvidenceKind.WRAP_PYFUNCTION in kinds
    assert BindingEvidenceKind.PYMODULE_ATTR in kinds


def test_pybind11_exact_and_inline() -> None:
    src = """
#include <pybind11/pybind11.h>
namespace py = pybind11;
PYBIND11_MODULE(_native, m) {
    m.def("solve", &engine::solve);
    m.def("add", [](int a, int b) { return a + b; });
}
"""
    edges = Pybind11BindingProvider().extract("file:///bindings.cpp", src)
    by_name = {e.python_name: e for e in edges}
    assert "solve" in by_name
    assert by_name["solve"].precision is BindingPrecision.EXACT
    assert by_name["solve"].native_symbol == "cpp:engine::solve"
    assert "add" in by_name
    assert by_name["add"].precision is BindingPrecision.INLINE
    assert "<lambda@" in by_name["add"].native_symbol


def test_cpython_pymethoddef() -> None:
    src = """
static PyMethodDef methods[] = {
    {"solve", py_solve, METH_VARARGS, nullptr},
    {nullptr, nullptr, 0, nullptr},
};
PyMODINIT_FUNC PyInit__native(void) {
    return PyModule_Create(&module);
}
"""
    edges = CPythonBindingProvider().extract("file:///ext.c", src)
    assert len(edges) == 1
    edge = edges[0]
    assert edge.python_symbol == "python:_native.solve"
    assert edge.native_symbol == "cpp:py_solve"
    assert edge.framework is BindingFramework.CPYTHON
    assert BindingEvidenceKind.PYMETHODDEF in {e.kind for e in edge.evidence}
    assert BindingEvidenceKind.PYINIT in {e.kind for e in edge.evidence}


def test_pyi_bridge_and_index_chain() -> None:
    stub_src = """
def fast_sum(a: int, b: int) -> int: ...
"""
    stubs = PyiBridgeProvider().extract_stubs("file:///_native.pyi", stub_src, module="_native")
    assert len(stubs) == 1
    assert stubs[0].python_symbol == "python:_native.fast_sum"

    rust = """
#[pyfunction]
#[pyo3(name = "fast_sum")]
fn fast_sum_impl(a: i64, b: i64) -> i64 { a + b }
#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(fast_sum_impl, m)?)?;
    Ok(())
}
"""
    index = BindingIndex()
    index.add_stub(stubs[0])
    index.add_edges(PyO3BindingProvider().extract("file:///lib.rs", rust))
    stub, edges = index.bridge_chain_for("fast_sum")
    assert stub is not None
    assert stub.module == "_native"
    assert len(edges) == 1
    assert edges[0].native_symbol == "rust:fast_sum_impl"


def test_service_advertises_ffi_bindings() -> None:
    rust = make_rust_language_service(bindings=(PyO3BindingProvider(),))
    assert rust.has_capability(LanguageCapability.FFI_BINDINGS)
    assert rust.bindings
    bare = make_rust_language_service()
    assert not bare.has_capability(LanguageCapability.FFI_BINDINGS)
    cpp = make_cpp_language_service(bindings=(Pybind11BindingProvider(), CPythonBindingProvider()))
    assert cpp.has_capability(LanguageCapability.FFI_BINDINGS)


def test_evidence_spans_are_source_spans() -> None:
    ev = BindingEvidence(
        kind=BindingEvidenceKind.PYI_DECL,
        uri="u",
        span=SourceSpan(0, 4),
        detail="def",
    )
    assert ev.span.length == 4
