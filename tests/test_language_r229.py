# -*- coding: utf-8 -*-
"""R229: advertised language capabilities must match provider APIs."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest
from app.language_services import LanguageServiceManager
from core.document_snapshot import DocumentSnapshot
from core.language import (
    LSP_EDITOR_CAPABILITIES,
    SEMANTIC_PROVIDER_CAPABILITIES,
    LanguageCapability,
    LanguageDescriptor,
    LanguageService,
    make_cpp_language_service,
    make_rust_language_service,
)
from ui.language_controller import DiagnosticsClaim, LanguageController

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
        if method == "exit":
            break
        if mid is None:
            continue
        if method == "initialize":
            write_msg({"jsonrpc": "2.0", "id": mid, "result": {"capabilities": {}}})
        elif method == "shutdown":
            write_msg({"jsonrpc": "2.0", "id": mid, "result": None})
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
    """Minimal LSP that answers initialize/shutdown."""
    path = tmp_path / "fake_r229_lsp.py"
    path.write_text(_FAKE_LSP, encoding="utf-8")
    return path


def test_semantic_provider_caps_exclude_unimplemented_apis() -> None:
    """DIAGNOSTICS / COMPLETION / SEMANTIC_TOKENS are not on SemanticProvider."""
    assert LanguageCapability.DIAGNOSTICS not in SEMANTIC_PROVIDER_CAPABILITIES
    assert LanguageCapability.COMPLETION not in SEMANTIC_PROVIDER_CAPABILITIES
    assert LanguageCapability.SEMANTIC_TOKENS not in SEMANTIC_PROVIDER_CAPABILITIES
    assert SEMANTIC_PROVIDER_CAPABILITIES == LSP_EDITOR_CAPABILITIES
    for cap in (
        LanguageCapability.OUTLINE,
        LanguageCapability.HOVER,
        LanguageCapability.DEFINITION,
        LanguageCapability.REFERENCES,
        LanguageCapability.RENAME,
        LanguageCapability.FORMAT,
    ):
        assert cap in SEMANTIC_PROVIDER_CAPABILITIES


def test_bare_service_advertises_no_semantic_caps() -> None:
    """Without a SemanticProvider, rust/cpp services advertise no editor caps."""
    rust = make_rust_language_service()
    cpp = make_cpp_language_service()
    assert rust.semantic is None and cpp.semantic is None
    for svc in (rust, cpp):
        for cap in SEMANTIC_PROVIDER_CAPABILITIES:
            assert not svc.has_capability(cap)
        assert not svc.has_capability(LanguageCapability.DIAGNOSTICS)
        assert not svc.has_capability(LanguageCapability.COMPLETION)
        assert not svc.has_capability(LanguageCapability.SEMANTIC_TOKENS)


def test_registered_lsp_does_not_claim_diagnostics(tmp_path: Path, fake_lsp: Path) -> None:
    """register_rust_lsp advertises only implemented semantic methods."""
    (tmp_path / "Cargo.toml").write_text("[package]\n", encoding="utf-8")
    mgr = LanguageServiceManager()
    mgr.register_rust_lsp(
        str(tmp_path),
        binary=sys.executable,
        allowlist=[sys.executable],
        extra_args=[str(fake_lsp)],
        attach_structural=False,
        attach_bindings=False,
        attach_tasks=False,
    )
    svc = mgr.registry.get("rust.lsp")
    assert svc.semantic is not None
    assert svc.capabilities == SEMANTIC_PROVIDER_CAPABILITIES
    assert LanguageCapability.DIAGNOSTICS not in svc.capabilities

    ctrl = LanguageController(mgr)
    doc = DocumentSnapshot(uri="file:///tmp/lib.rs", text="fn x() {}\n", language_id="rust")
    assert ctrl.supports(doc, LanguageCapability.HOVER) is True
    assert ctrl.supports(doc, LanguageCapability.DIAGNOSTICS) is False
    assert ctrl.supports(doc, LanguageCapability.COMPLETION) is False
    assert ctrl.supports(doc, LanguageCapability.SEMANTIC_TOKENS) is False
    policy = ctrl.diagnostics_policy(doc)
    assert policy.claim is DiagnosticsClaim.UNAVAILABLE
    assert "DIAGNOSTICS" in policy.reason
    mgr.shutdown()


def test_manual_diagnostics_cap_still_needs_semantic() -> None:
    """Even if DIAGNOSTICS is advertised, supports() requires a provider (R229)."""
    mgr = LanguageServiceManager()
    svc = LanguageService(
        descriptor=LanguageDescriptor("zig", frozenset({".zig"})),
        capabilities=frozenset({LanguageCapability.DIAGNOSTICS}),
        service_id="zig.diag-only",
        semantic=None,
    )
    mgr.registry.register(svc)
    ctrl = LanguageController(mgr)
    doc = DocumentSnapshot(uri="file:///a.zig", text="x", language_id="zig")
    assert ctrl.supports(doc, LanguageCapability.DIAGNOSTICS) is False
    policy = ctrl.diagnostics_policy(doc)
    assert policy.claim is DiagnosticsClaim.UNAVAILABLE
    assert policy.readiness is None
