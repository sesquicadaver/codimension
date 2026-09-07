# -*- coding: utf-8 -*-
"""R230: LanguageServiceManager workspace attach/detach + IDE composition."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest
from app.language_services import (
    ENV_RUST_ANALYZER,
    LanguageServiceManager,
)
from core.document_snapshot import DocumentSnapshot
from core.feature_flags import FLAG_LANGUAGE_SERVICES, FeatureFlagsStore
from core.language import LanguageCapability
from ui.language_controller import LanguageController


@pytest.fixture()
def enabled_store(tmp_path: Path) -> FeatureFlagsStore:
    store = FeatureFlagsStore(str(tmp_path / "flags.json"))
    store.set_enabled(FLAG_LANGUAGE_SERVICES, True)
    return store


@pytest.fixture()
def fake_lsp(tmp_path: Path) -> Path:
    """Minimal LSP that answers initialize/shutdown."""
    path = tmp_path / "fake_r230_lsp.py"
    path.write_text(
        textwrap.dedent(
            r"""
            import json, sys
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
                return json.loads(sys.stdin.buffer.read(n).decode("utf-8"))
            def write_msg(obj):
                raw = json.dumps(obj, separators=(",", ":")).encode("utf-8")
                sys.stdout.buffer.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii"))
                sys.stdout.buffer.write(raw)
                sys.stdout.buffer.flush()
            while True:
                msg = read_msg()
                if msg is None:
                    break
                if msg.get("method") == "exit":
                    break
                mid = msg.get("id")
                if mid is None:
                    continue
                if msg.get("method") == "initialize":
                    write_msg({"jsonrpc": "2.0", "id": mid, "result": {"capabilities": {}}})
                elif msg.get("method") == "shutdown":
                    write_msg({"jsonrpc": "2.0", "id": mid, "result": None})
                else:
                    write_msg({
                        "jsonrpc": "2.0",
                        "id": mid,
                        "error": {"code": -32601, "message": "unknown"},
                    })
            """
        ),
        encoding="utf-8",
    )
    return path


def test_attach_disabled_leaves_empty_registry(tmp_path: Path) -> None:
    store = FeatureFlagsStore(str(tmp_path / "off.json"))
    mgr = LanguageServiceManager()
    assert mgr.attach_workspace(str(tmp_path), store=store, environ={}) is False
    assert mgr.workspace_root is None
    assert mgr.registry.list_services() == ()


def test_attach_python_only_when_no_markers(tmp_path: Path, enabled_store: FeatureFlagsStore) -> None:
    mgr = LanguageServiceManager()
    assert mgr.attach_workspace(str(tmp_path), store=enabled_store, environ={}) is True
    assert mgr.workspace_root == str(tmp_path.resolve())
    assert mgr.registry.service_ids() == ("python.headless",)
    mgr.detach_workspace()
    assert mgr.workspace_root is None
    assert mgr.registry.list_services() == ()


def test_attach_rust_headless_without_binary(tmp_path: Path, enabled_store: FeatureFlagsStore) -> None:
    (tmp_path / "Cargo.toml").write_text("[package]\nname='x'\n", encoding="utf-8")
    mgr = LanguageServiceManager()
    assert mgr.attach_workspace(
        str(tmp_path),
        store=enabled_store,
        environ={},
        attach_structural=False,
        attach_bindings=False,
        attach_tasks=True,
    )
    assert mgr.registry.has("python.headless")
    rust = mgr.registry.get("rust.lsp")
    assert rust.semantic is None
    assert rust.has_capability(LanguageCapability.BUILD_TASKS)
    assert not rust.has_capability(LanguageCapability.HOVER)
    mgr.detach_workspace()


def test_attach_env_binary_registers_semantic(tmp_path: Path, enabled_store: FeatureFlagsStore) -> None:
    """Absolute CDM_RUST_ANALYZER registers a SemanticProvider (spawn stays lazy)."""
    (tmp_path / "Cargo.toml").write_text("[package]\nname='x'\n", encoding="utf-8")
    mgr = LanguageServiceManager()
    assert mgr.attach_workspace(
        str(tmp_path),
        store=enabled_store,
        environ={ENV_RUST_ANALYZER: sys.executable},
        attach_structural=False,
        attach_bindings=False,
        attach_tasks=False,
    )
    rust = mgr.registry.get("rust.lsp")
    assert rust.semantic is not None
    assert rust.has_capability(LanguageCapability.HOVER)
    ctrl = LanguageController(mgr)
    doc = DocumentSnapshot(uri="file:///tmp/lib.rs", text="fn x() {}\n", language_id="rust")
    assert ctrl.supports(doc, LanguageCapability.HOVER) is True
    mgr.detach_workspace()


def test_reattach_replaces_previous_workspace(tmp_path: Path, enabled_store: FeatureFlagsStore) -> None:
    first = tmp_path / "a"
    second = tmp_path / "b"
    first.mkdir()
    second.mkdir()
    (first / "Cargo.toml").write_text("[package]\n", encoding="utf-8")
    mgr = LanguageServiceManager()
    mgr.attach_workspace(
        str(first),
        store=enabled_store,
        environ={},
        attach_structural=False,
        attach_bindings=False,
        attach_tasks=False,
    )
    assert mgr.registry.has("rust.lsp")
    mgr.attach_workspace(
        str(second),
        store=enabled_store,
        environ={},
        attach_structural=False,
        attach_bindings=False,
        attach_tasks=False,
    )
    assert mgr.workspace_root == str(second.resolve())
    assert not mgr.registry.has("rust.lsp")
    assert mgr.registry.has("python.headless")
    mgr.detach_workspace()


def test_globals_wires_language_services_lifecycle() -> None:
    """GlobalData owns LanguageServiceManager and hooks ApplicationServices."""
    text = (
        Path(__file__).resolve().parents[1].joinpath("codimension", "utils", "globals.py").read_text(encoding="utf-8")
    )
    assert "LanguageServiceManager" in text
    assert "self._languageServices = None" in text
    assert "def languageServices(self):" in text
    assert "after_load=self.__attachLanguageWorkspace" in text
    assert "before_unload=self.__detachLanguageWorkspace" in text


def test_mainwindow_wires_language_controller() -> None:
    text = (
        Path(__file__).resolve().parents[1].joinpath("codimension", "ui", "mainwindow.py").read_text(encoding="utf-8")
    )
    assert "def languageController(self):" in text
    assert "LanguageController(GlobalData().languageServices)" in text
    assert "self._languageController = None" in text
