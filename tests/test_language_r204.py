# -*- coding: utf-8 -*-
"""R204: capability-driven LanguageController (no if language == …)."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest
from app.language_services import LanguageServiceManager
from core.document_snapshot import DocumentSnapshot
from core.language import LanguageCapability, make_python_language_service
from core.semantic import SemanticReadiness
from ui.language_controller import (
    CapabilityDenied,
    DiagnosticsClaim,
    LanguageController,
)

_FAKE_LSP = textwrap.dedent(
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
                "result": {"capabilities": {}, "serverInfo": {"name": "fake-r204"}},
            })
        elif method == "shutdown":
            write_msg({"jsonrpc": "2.0", "id": mid, "result": None})
        elif method == "textDocument/hover":
            write_msg({
                "jsonrpc": "2.0",
                "id": mid,
                "result": {"contents": {"kind": "markdown", "value": "hover-ok"}},
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
                        "end": {"line": 0, "character": 2},
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
                        "end": {"line": 0, "character": 2},
                    },
                }],
            })
        elif method == "textDocument/documentSymbol":
            write_msg({
                "jsonrpc": "2.0",
                "id": mid,
                "result": [{
                    "name": "item",
                    "kind": 12,
                    "range": {
                        "start": {"line": 0, "character": 0},
                        "end": {"line": 0, "character": 4},
                    },
                    "selectionRange": {
                        "start": {"line": 0, "character": 0},
                        "end": {"line": 0, "character": 4},
                    },
                    "children": [],
                }],
            })
        elif method == "textDocument/formatting":
            write_msg({
                "jsonrpc": "2.0",
                "id": mid,
                "result": [{
                    "range": {
                        "start": {"line": 0, "character": 0},
                        "end": {"line": 0, "character": 4},
                    },
                    "newText": "fmt()",
                }],
            })
        elif method == "textDocument/rename":
            uri = (params.get("textDocument") or {}).get("uri")
            new_name = params.get("newName", "x")
            write_msg({
                "jsonrpc": "2.0",
                "id": mid,
                "result": {
                    "changes": {
                        uri: [{
                            "range": {
                                "start": {"line": 0, "character": 0},
                                "end": {"line": 0, "character": 4},
                            },
                            "newText": new_name,
                        }]
                    }
                },
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
def fake_lsp(tmp_path: Path) -> Path:
    path = tmp_path / "fake_r204_lsp.py"
    path.write_text(_FAKE_LSP, encoding="utf-8")
    return path


def test_controller_source_has_no_language_equals() -> None:
    src = Path(__file__).resolve().parents[1] / "codimension" / "ui" / "language_controller.py"
    text = src.read_text(encoding="utf-8")
    assert "if language ==" not in text
    assert 'language == "' not in text
    assert "language == '" not in text


def test_resolve_by_extension_and_capability_gate(tmp_path: Path, fake_lsp: Path) -> None:
    (tmp_path / "Cargo.toml").write_text("[package]\n", encoding="utf-8")
    mgr = LanguageServiceManager()
    mgr.register_rust_lsp(
        str(tmp_path),
        binary=sys.executable,
        allowlist=[sys.executable],
        extra_args=[str(fake_lsp)],
    )
    ctrl = LanguageController(mgr)
    doc = DocumentSnapshot(
        uri="file:///tmp/lib.rs",
        text="fn xx() {}\n",
        language_id="",  # resolve via extension
    )
    assert ctrl.supports(doc, LanguageCapability.HOVER) is True
    hover = ctrl.hover(doc, 3)
    assert hover is not None and hover.contents == "hover-ok"
    assert ctrl.definition(doc, 3)
    assert ctrl.references(doc, 3)
    assert ctrl.outline(doc)[0].name == "item"
    fmt = ctrl.format_preview(doc)
    assert fmt and fmt[0].edit.new_text == "fmt()"
    ren = ctrl.rename_preview(doc, 3, "yy")
    assert ren and ren[0].edit.new_text == "yy"
    policy = ctrl.diagnostics_policy(doc)
    assert policy.claim is DiagnosticsClaim.FULL
    assert policy.readiness is SemanticReadiness.READY
    mgr.shutdown()


def test_python_headless_no_semantic_denies_hover() -> None:
    mgr = LanguageServiceManager()
    mgr.registry.register(make_python_language_service())
    ctrl = LanguageController(mgr)
    doc = DocumentSnapshot(uri="file:///a.py", text="x=1\n", language_id="python")
    assert ctrl.supports(doc, LanguageCapability.OUTLINE) is False
    assert ctrl.supports(doc, LanguageCapability.DEFINITION) is False
    with pytest.raises(CapabilityDenied):
        ctrl.hover(doc, 0)


def test_cpp_degraded_diagnostics_policy(tmp_path: Path, fake_lsp: Path) -> None:
    mgr = LanguageServiceManager()
    mgr.register_cpp_lsp(
        str(tmp_path),
        binary=sys.executable,
        allowlist=[sys.executable],
        extra_args=[str(fake_lsp)],
    )
    ctrl = LanguageController(mgr)
    doc = DocumentSnapshot(uri="file:///a.cpp", text="int x;\n", language_id="cpp")
    policy = ctrl.diagnostics_policy(doc)
    assert policy.claim is DiagnosticsClaim.DEGRADED
    assert policy.readiness is SemanticReadiness.DEGRADED
    mgr.shutdown()


def test_missing_capability_raises(tmp_path: Path, fake_lsp: Path) -> None:
    from core.language import (
        LanguageCapability as Cap,
    )
    from core.language import (
        LanguageDescriptor,
        LanguageService,
    )
    from infrastructure.lsp_semantic import (
        LspSemanticConfig,
        LspSemanticProvider,
    )

    mgr = LanguageServiceManager()
    cfg = LspSemanticConfig(
        language_id="zig",
        workspace_root=str(tmp_path),
        command=(sys.executable, str(fake_lsp)),
        allowlist=(sys.executable,),
        provider_id="lsp.zig",
    )
    semantic = LspSemanticProvider(mgr.lsp_processes, cfg, readiness=SemanticReadiness.READY)
    # Advertise hover only — format must be denied
    svc = LanguageService(
        descriptor=LanguageDescriptor("zig", frozenset({".zig"})),
        capabilities=frozenset({Cap.HOVER}),
        service_id="zig.lsp",
        semantic=semantic,
    )
    mgr.registry.register(svc)
    ctrl = LanguageController(mgr)
    doc = DocumentSnapshot(uri="file:///a.zig", text="x", language_id="zig")
    assert ctrl.supports(doc, Cap.HOVER) is True
    with pytest.raises(CapabilityDenied, match="format"):
        ctrl.format_preview(doc)
    mgr.shutdown()
