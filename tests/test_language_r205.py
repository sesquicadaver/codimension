# -*- coding: utf-8 -*-
"""R205: Tree-sitter StructuralGraph + semantic_role mapping."""

from __future__ import annotations

import inspect

import pytest
from core.document_snapshot import DocumentSnapshot
from core.language import LanguageCapability, make_cpp_language_service, make_rust_language_service
from core.language_policy import PolicyCapability, allow_tree_parse
from core.structural import (
    SemanticRole,
    StructuralEdgeKind,
    StructuralGraph,
    StructuralNode,
    StructuralProvider,
)
from core.symbol_index import SourceSpan
from infrastructure.tree_sitter_structural import (
    CPP_NODE_ROLES,
    RUST_NODE_ROLES,
    role_for_native_kind,
    try_build_tree_sitter_structural_provider,
    unicode_span_from_bytes,
    utf8_byte_to_unicode_offset,
)

tree_sitter = pytest.importorskip("tree_sitter")
pytest.importorskip("tree_sitter_rust")
pytest.importorskip("tree_sitter_cpp")


def test_semantic_role_mapping_tables() -> None:
    assert role_for_native_kind("rust", "match_expression") is SemanticRole.BRANCH
    assert role_for_native_kind("rust", "loop_expression") is SemanticRole.LOOP
    assert role_for_native_kind("rust", "try_expression") is SemanticRole.EARLY_EXIT
    assert role_for_native_kind("cpp", "switch_statement") is SemanticRole.BRANCH
    assert role_for_native_kind("cpp", "for_range_loop") is SemanticRole.LOOP
    assert role_for_native_kind("cpp", "throw_statement") is SemanticRole.EXCEPTION_EXIT
    assert role_for_native_kind("rust", "identifier") is None
    assert "match_expression" in RUST_NODE_ROLES
    assert "switch_statement" in CPP_NODE_ROLES


def test_utf8_byte_to_unicode_offset() -> None:
    text = 'fn f() { let x = "ї"; }'
    start = utf8_byte_to_unicode_offset(text, 17)
    end = utf8_byte_to_unicode_offset(text, 21)
    assert text[start:end] == '"ї"'
    span = unicode_span_from_bytes(text, 17, 21)
    assert span == SourceSpan(start, end)


def test_tree_parse_policy_allows() -> None:
    assert allow_tree_parse() is True
    assert PolicyCapability.TREE_PARSE.value == "tree_parse"


def test_structural_graph_is_not_cfg() -> None:
    from core import structural as structural_mod
    from infrastructure import tree_sitter_structural as ts_mod

    for mod in (structural_mod, ts_mod):
        doc = inspect.getdoc(mod) or ""
        assert "not" in doc.lower()
        assert "cfg" in doc.lower()
        assert "compiler" in doc.lower() or "control-flow" in doc.lower() or "control flow" in doc.lower()


def test_rust_structural_graph_roles() -> None:
    provider = try_build_tree_sitter_structural_provider("rust")
    assert provider is not None
    assert isinstance(provider, StructuralProvider)
    src = """
fn main() {
    match x { 1 => {}, _ => {} }
    loop { break; }
    while true { continue; }
    for i in 0..1 { return; }
    let y = foo()?;
    bar!();
    #[pyfunction]
    fn exported() {}
}
"""
    doc = DocumentSnapshot(uri="file:///tmp/main.rs", text=src, language_id="rust")
    graph = provider.build_graph(doc)
    assert graph.language_id == "rust"
    assert graph.root_id
    roles = {n.semantic_role for n in graph.nodes.values()}
    assert SemanticRole.MODULE in roles
    assert SemanticRole.FUNCTION in roles
    assert SemanticRole.BRANCH in roles
    assert SemanticRole.LOOP in roles
    assert SemanticRole.BREAK in roles
    assert SemanticRole.CONTINUE in roles
    assert SemanticRole.RETURN in roles
    assert SemanticRole.EARLY_EXIT in roles
    assert SemanticRole.MACRO in roles
    assert SemanticRole.FFI_BOUNDARY in roles
    # Containment only — not CFG successor kinds.
    assert all(e.kind is StructuralEdgeKind.CONTAINS for e in graph.edges)
    assert graph.nodes_of_role(SemanticRole.BRANCH)
    children = graph.children(graph.root_id)
    assert children


def test_cpp_structural_graph_roles() -> None:
    provider = try_build_tree_sitter_structural_provider("cpp")
    assert provider is not None
    src = """
namespace N {
void f() {
  switch (x) { case 1: break; default: throw 1; }
  for (auto& i : v) { continue; }
  while (1) {}
  return;
}
}
"""
    doc = DocumentSnapshot(uri="file:///tmp/main.cpp", text=src, language_id="cpp")
    graph = provider.build_graph(doc)
    roles = {n.semantic_role for n in graph.nodes.values()}
    assert SemanticRole.MODULE in roles
    assert SemanticRole.NAMESPACE in roles
    assert SemanticRole.FUNCTION in roles
    assert SemanticRole.BRANCH in roles
    assert SemanticRole.LOOP in roles
    assert SemanticRole.EXCEPTION_EXIT in roles
    assert SemanticRole.BREAK in roles
    assert SemanticRole.CONTINUE in roles
    assert SemanticRole.RETURN in roles


def test_service_advertises_structural_graph() -> None:
    provider = try_build_tree_sitter_structural_provider("rust")
    assert provider is not None
    svc = make_rust_language_service(structural=provider)
    assert svc.has_capability(LanguageCapability.STRUCTURAL_GRAPH)
    assert svc.structural is provider
    bare = make_rust_language_service()
    assert not bare.has_capability(LanguageCapability.STRUCTURAL_GRAPH)
    cpp = make_cpp_language_service(structural=try_build_tree_sitter_structural_provider("cpp"))
    assert cpp.has_capability(LanguageCapability.STRUCTURAL_GRAPH)


def test_manual_structural_graph_protocol() -> None:
    """Fake provider satisfies the Protocol without Tree-sitter."""

    class FakeProvider:
        @property
        def provider_id(self) -> str:
            return "fake.structural"

        @property
        def language_id(self) -> str:
            return "rust"

        def build_graph(self, document: DocumentSnapshot) -> StructuralGraph:
            node = StructuralNode(
                id="n1",
                native_kind="match_expression",
                semantic_role=SemanticRole.BRANCH,
                span=SourceSpan(0, len(document.text)),
                label="match",
            )
            g = StructuralGraph(language_id="rust", root_id="n1")
            g.nodes["n1"] = node
            return g

    fake: StructuralProvider = FakeProvider()
    g = fake.build_graph(DocumentSnapshot(uri="u", text="match"))
    assert g.nodes["n1"].semantic_role is SemanticRole.BRANCH


def test_unsupported_language_raises() -> None:
    from infrastructure.tree_sitter_structural import TreeSitterStructuralProvider

    with pytest.raises(ValueError):
        TreeSitterStructuralProvider("python")
    assert try_build_tree_sitter_structural_provider("python") is None
