# -*- coding: utf-8 -*-
"""R207: DependencyEdgeKind + cross-language navigation."""

from __future__ import annotations

from core.bindings import BindingIndex
from core.cross_language_nav import (
    navigate_native_to_python,
    navigate_python_export_to_native,
    resolve_cross_language_target,
)
from core.dependency_edges import (
    DependencyEdgeKind,
    build_polyglot_graph_from_bindings,
    ingest_python_import_edges,
)
from infrastructure.ffi_bindings import PyiBridgeProvider, PyO3BindingProvider
from utils.dependency_graph import (
    DependencyEdge,
    DependencyGraph,
    DependencyNode,
    build_dependency_graph_from_sources,
    to_polyglot_graph,
)


def test_dependency_edge_kind_values() -> None:
    assert DependencyEdgeKind.PYTHON_IMPORT.value == "python.import"
    assert DependencyEdgeKind.FFI_BINDING.value == "ffi.binding"
    assert DependencyEdgeKind.RUST_USE.value == "rust.use"
    assert DependencyEdgeKind.CPP_INCLUDE.value == "cpp.include"


def test_python_import_edges_default_kind() -> None:
    graph = build_dependency_graph_from_sources(
        [
            ("/tmp/proj/a.py", "import b\n"),
            ("/tmp/proj/b.py", "x = 1\n"),
        ],
        root="/tmp/proj",
    )
    assert graph.edges
    assert all(e.kind is DependencyEdgeKind.PYTHON_IMPORT for e in graph.edges)
    payload = graph.edges[0].to_dict()
    assert payload["kind"] == "python.import"


def test_to_polyglot_graph_preserves_imports() -> None:
    py = DependencyGraph()
    py.add_node(DependencyNode(id="a", kind="file", label="a"))
    py.add_node(DependencyNode(id="b", kind="file", label="b"))
    py.add_edge(DependencyEdge(source="a", target="b", labels=("b",)))
    poly = to_polyglot_graph(py)
    assert "a" in poly.nodes
    assert poly.edges_of_kind(DependencyEdgeKind.PYTHON_IMPORT)
    assert poly.successors("a") == ("b",)


def test_ffi_and_stub_in_polyglot_graph() -> None:
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
    stubs = PyiBridgeProvider().extract_stubs("file:///_native.pyi", "def fast_sum(a: int, b: int) -> int: ...\n")
    index = BindingIndex()
    index.add_stub(stubs[0])
    index.add_edges(PyO3BindingProvider().extract("file:///lib.rs", rust))
    poly = build_polyglot_graph_from_bindings(index)
    ffi = poly.edges_of_kind(DependencyEdgeKind.FFI_BINDING)
    assert len(ffi) == 1
    assert ffi[0].source == "python:_native.fast_sum"
    assert ffi[0].target == "rust:fast_sum_impl"
    assert poly.cross_language_neighbors("python:_native.fast_sum")


def test_navigate_python_to_native_with_pyi() -> None:
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
    index.add_stub(
        PyiBridgeProvider().extract_stubs(
            "file:///_native.pyi",
            "def fast_sum(a: int, b: int) -> int: ...\n",
            module="_native",
        )[0]
    )
    index.add_edges(PyO3BindingProvider().extract("file:///lib.rs", rust))
    hops = navigate_python_export_to_native(index, "fast_sum")
    assert len(hops) == 3
    assert hops[0].role == "pyi_stub"
    assert hops[1].role == "python_export"
    assert hops[2].role == "native_impl"
    assert hops[2].symbol == "rust:fast_sum_impl"
    assert hops[2].language_id == "rust"

    back = navigate_native_to_python(index, "rust:fast_sum_impl")
    assert back[0].role == "native_impl"
    assert any(h.role == "python_export" for h in back)

    terminal = resolve_cross_language_target(index, from_symbol="fast_sum", toward="native")
    assert terminal is not None
    assert terminal.symbol == "rust:fast_sum_impl"


def test_no_navigation_without_evidence() -> None:
    index = BindingIndex()
    assert navigate_python_export_to_native(index, "missing") == ()
    assert resolve_cross_language_target(index, from_symbol="missing", toward="native") is None


def test_ingest_python_imports_into_polyglot() -> None:
    from core.dependency_edges import PolyglotDependencyGraph

    g = PolyglotDependencyGraph()
    ingest_python_import_edges(g, edges=(("pkg.a", "pkg.b", ("b",)),))
    assert g.edges[0].kind is DependencyEdgeKind.PYTHON_IMPORT
