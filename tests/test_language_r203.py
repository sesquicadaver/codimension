# -*- coding: utf-8 -*-
"""R203: Rust/C++ descriptors, readiness, LspSemanticProvider."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest
from app.language_services import LanguageServiceManager
from core.document_snapshot import DocumentSnapshot
from core.feature_flags import FLAG_LANGUAGE_SERVICES, FeatureFlagsStore
from core.language import (
    CPP_DESCRIPTOR,
    RUST_DESCRIPTOR,
    LanguageCapability,
    make_cpp_language_service,
    make_rust_language_service,
)
from core.language_workspace import (
    assess_cpp_semantic_readiness,
    assess_rust_semantic_readiness,
    find_compile_commands_json,
    find_marked_root,
)
from core.semantic import SemanticProvider, SemanticReadiness
from infrastructure.lsp_semantic import LspSemanticConfig

_FAKE_SEMANTIC_LSP = textwrap.dedent(
    r"""
    import json
    import sys

    def read_msg():
        headers = {}
        while True:
            line = sys.stdin.buffer.readline()
            if not line:
                return None
            if line in (b"\r\n", b"\n"):
                break
            key, val = line.decode("ascii").split(":", 1)
            headers[key.strip().lower()] = val.strip()
        n = int(headers["content-length"])
        body = sys.stdin.buffer.read(n)
        return json.loads(body.decode("utf-8"))

    def write_msg(obj):
        raw = json.dumps(obj, separators=(",", ":")).encode("utf-8")
        sys.stdout.buffer.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii"))
        sys.stdout.buffer.write(raw)
        sys.stdout.buffer.flush()

    while True:
        msg = read_msg()
        if msg is None:
            break
        method = msg.get("method")
        mid = msg.get("id")
        params = msg.get("params") or {}
        if method == "exit":
            break
        if method in ("textDocument/didOpen", "initialized", "$/cancelRequest"):
            continue
        if mid is None:
            continue
        if method == "initialize":
            write_msg({
                "jsonrpc": "2.0",
                "id": mid,
                "result": {"capabilities": {}, "serverInfo": {"name": "fake-semantic"}},
            })
        elif method == "shutdown":
            write_msg({"jsonrpc": "2.0", "id": mid, "result": None})
        elif method == "textDocument/hover":
            write_msg({
                "jsonrpc": "2.0",
                "id": mid,
                "result": {
                    "contents": {"kind": "markdown", "value": "fn answer"},
                    "range": {
                        "start": {"line": 0, "character": 0},
                        "end": {"line": 0, "character": 3},
                    },
                },
            })
        elif method == "textDocument/definition":
            uri = (params.get("textDocument") or {}).get("uri")
            write_msg({
                "jsonrpc": "2.0",
                "id": mid,
                "result": {
                    "uri": uri,
                    "range": {
                        "start": {"line": 0, "character": 0},
                        "end": {"line": 0, "character": 3},
                    },
                },
            })
        elif method == "textDocument/references":
            uri = (params.get("textDocument") or {}).get("uri")
            write_msg({
                "jsonrpc": "2.0",
                "id": mid,
                "result": [{
                    "uri": uri,
                    "range": {
                        "start": {"line": 0, "character": 0},
                        "end": {"line": 0, "character": 3},
                    },
                }],
            })
        elif method == "textDocument/documentSymbol":
            write_msg({
                "jsonrpc": "2.0",
                "id": mid,
                "result": [{
                    "name": "answer",
                    "kind": 12,
                    "range": {
                        "start": {"line": 0, "character": 0},
                        "end": {"line": 0, "character": 10},
                    },
                    "selectionRange": {
                        "start": {"line": 0, "character": 0},
                        "end": {"line": 0, "character": 6},
                    },
                    "children": [],
                }],
            })
        else:
            write_msg({
                "jsonrpc": "2.0",
                "id": mid,
                "error": {"code": -32601, "message": f"unknown {method}"},
            })
    """
)


@pytest.fixture()
def fake_semantic_lsp(tmp_path: Path) -> Path:
    path = tmp_path / "fake_semantic_lsp.py"
    path.write_text(_FAKE_SEMANTIC_LSP, encoding="utf-8")
    return path


def test_rust_cpp_descriptors() -> None:
    assert RUST_DESCRIPTOR.language_id == "rust"
    assert ".rs" in RUST_DESCRIPTOR.extensions
    assert RUST_DESCRIPTOR.server_name == "rust-analyzer"
    assert "Cargo.toml" in RUST_DESCRIPTOR.root_markers
    assert CPP_DESCRIPTOR.server_name == "clangd"
    assert ".cpp" in CPP_DESCRIPTOR.extensions
    svc = make_rust_language_service()
    assert svc.service_id == "rust.lsp"
    assert svc.has_capability(LanguageCapability.HOVER)
    assert svc.semantic is None
    assert make_cpp_language_service().service_id == "cpp.lsp"


def test_cpp_readiness_compile_commands(tmp_path: Path) -> None:
    assert assess_cpp_semantic_readiness(str(tmp_path)) is SemanticReadiness.DEGRADED
    assert find_compile_commands_json(str(tmp_path)) is None
    (tmp_path / "build").mkdir()
    cc = tmp_path / "build" / "compile_commands.json"
    cc.write_text("[]", encoding="utf-8")
    assert find_compile_commands_json(str(tmp_path)) == str(cc)
    assert assess_cpp_semantic_readiness(str(tmp_path)) is SemanticReadiness.READY


def test_rust_readiness_cargo(tmp_path: Path) -> None:
    assert assess_rust_semantic_readiness(str(tmp_path)) is SemanticReadiness.DEGRADED
    (tmp_path / "Cargo.toml").write_text("[package]\nname='x'\n", encoding="utf-8")
    assert assess_rust_semantic_readiness(str(tmp_path)) is SemanticReadiness.READY


def test_find_marked_root(tmp_path: Path) -> None:
    nested = tmp_path / "src" / "lib.rs"
    nested.parent.mkdir(parents=True)
    nested.write_text("fn x() {}", encoding="utf-8")
    (tmp_path / "Cargo.toml").write_text("[package]\n", encoding="utf-8")
    assert find_marked_root(str(nested), ("Cargo.toml",)) == str(tmp_path)


def test_lsp_semantic_provider_hover_definition(tmp_path: Path, fake_semantic_lsp: Path) -> None:
    (tmp_path / "Cargo.toml").write_text("[package]\n", encoding="utf-8")
    mgr = LanguageServiceManager()
    store = FeatureFlagsStore(str(tmp_path / "flags.json"))
    store.set_enabled(FLAG_LANGUAGE_SERVICES, True)
    assert mgr.ensure_defaults(store=store) is True
    sid = mgr.register_rust_lsp(
        str(tmp_path),
        binary=sys.executable,
        allowlist=[sys.executable],
        extra_args=[str(fake_semantic_lsp)],
    )
    assert sid == "rust.lsp"
    service = mgr.registry.get("rust.lsp")
    semantic = service.semantic
    assert semantic is not None
    assert isinstance(semantic, SemanticProvider)
    assert semantic.readiness() is SemanticReadiness.READY
    assert semantic.claims_full_diagnostics() is True

    doc = DocumentSnapshot(
        uri="file:///tmp/lib.rs",
        text="fn answer() {}\n",
        language_id="rust",
    )
    hover = semantic.hover(doc, 3)
    assert hover is not None
    assert "answer" in hover.contents
    defs = semantic.definition(doc, 3)
    assert len(defs) == 1
    assert defs[0].uri == doc.uri
    refs = semantic.references(doc, 3)
    assert len(refs) == 1
    outline = semantic.document_symbols(doc)
    assert outline[0].name == "answer"
    mgr.shutdown()


def test_cpp_register_degraded_without_compile_db(tmp_path: Path, fake_semantic_lsp: Path) -> None:
    mgr = LanguageServiceManager()
    mgr.register_cpp_lsp(
        str(tmp_path),
        binary=sys.executable,
        allowlist=[sys.executable],
        extra_args=[str(fake_semantic_lsp)],
    )
    semantic = mgr.registry.get("cpp.lsp").semantic
    assert semantic is not None
    assert semantic.readiness() is SemanticReadiness.DEGRADED
    assert semantic.claims_full_diagnostics() is False
    mgr.shutdown()


def test_lsp_semantic_config_defaults() -> None:
    cfg = LspSemanticConfig(
        language_id="rust",
        workspace_root="/tmp/ws",
        command=("/usr/bin/rust-analyzer",),
        allowlist=("/usr/bin/rust-analyzer",),
    )
    assert cfg.provider_id == "lsp.rust"
    assert cfg.language_id_for_did_open == "rust"
