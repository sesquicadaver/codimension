# -*- coding: utf-8 -*-
"""R242: Python headless semantic + buffer sync + supports() alignment."""

from __future__ import annotations

from pathlib import Path

from app.language_services import LanguageServiceManager
from core.document_snapshot import DocumentSnapshot
from core.document_store import DocumentStore
from core.feature_flags import FLAG_LANGUAGE_SERVICES, FeatureFlagsStore
from core.language import LanguageCapability, make_python_language_service
from infrastructure.file_uri import path_to_file_uri
from infrastructure.python_semantic import PythonHeadlessSemanticProvider, word_at_offset
from ui.language_controller import CapabilityDenied, LanguageController


def test_word_at_offset() -> None:
    text = "def hello_world():\n    return 1\n"
    assert word_at_offset(text, text.index("hello")) == "hello_world"
    assert word_at_offset(text, text.index("_world")) == "hello_world"
    assert word_at_offset(text, 0) == "def"
    assert word_at_offset("   ", 1) == ""


def test_python_headless_semantic_definition_and_outline() -> None:
    src = "def alpha():\n    return 1\n\nx = alpha()\n"
    provider = PythonHeadlessSemanticProvider()
    doc = DocumentSnapshot(uri="file:///tmp/r242.py", text=src, language_id="python")
    offset = src.rindex("alpha")
    defs = provider.definition(doc, offset)
    assert len(defs) == 1
    assert defs[0].span.start == src.index("alpha")
    refs = provider.references(doc, offset)
    assert len(refs) >= 2
    names = {sym.name for sym in provider.document_symbols(doc)}
    assert "alpha" in names
    assert provider.hover(doc, offset) is None
    assert provider.format_document(doc) == ()


def test_ensure_defaults_binds_python_semantic(tmp_path: Path) -> None:
    store = FeatureFlagsStore(str(tmp_path / "flags.json"))
    store.set_enabled(FLAG_LANGUAGE_SERVICES, True)
    mgr = LanguageServiceManager()
    assert mgr.ensure_defaults(store=store, environ={}) is True
    service = mgr.registry.get("python.headless")
    assert service.semantic is not None
    assert service.semantic.provider_id == "python.headless.brief"
    ctrl = LanguageController(mgr)
    doc = DocumentSnapshot(uri="file:///a.py", text="def f():\n    pass\n", language_id="python")
    assert ctrl.supports(doc, LanguageCapability.OUTLINE) is True
    assert ctrl.supports(doc, LanguageCapability.DEFINITION) is True
    assert ctrl.supports(doc, LanguageCapability.REFERENCES) is True
    assert ctrl.supports(doc, LanguageCapability.HOVER) is False
    outline = ctrl.outline(doc)
    assert any(sym.name == "f" for sym in outline)
    with __import__("pytest").raises(CapabilityDenied):
        ctrl.hover(doc, 0)
    mgr.shutdown()


def test_python_stub_without_semantic_still_denies() -> None:
    mgr = LanguageServiceManager()
    mgr.registry.register(make_python_language_service())
    ctrl = LanguageController(mgr)
    doc = DocumentSnapshot(uri="file:///a.py", text="x=1\n", language_id="python")
    assert ctrl.supports(doc, LanguageCapability.OUTLINE) is False
    assert ctrl.supports(doc, LanguageCapability.DEFINITION) is False


def test_buffer_open_change_close_sync(tmp_path: Path) -> None:
    store = FeatureFlagsStore(str(tmp_path / "flags.json"))
    store.set_enabled(FLAG_LANGUAGE_SERVICES, True)
    mgr = LanguageServiceManager()
    assert mgr.attach_workspace(str(tmp_path), store=store, environ={}) is True
    assert isinstance(mgr.document_store, DocumentStore)
    ctrl = LanguageController(mgr)
    path = tmp_path / "mod.py"
    path.write_text("def g():\n    return 2\n", encoding="utf-8")
    uri = path_to_file_uri(str(path))
    opened = ctrl.snapshot_for_buffer(path=str(path), text=path.read_text(encoding="utf-8"), version=0)
    assert opened is not None
    ctrl.notify_buffer_opened(opened)
    assert mgr.document_store.get(uri) is not None
    assert mgr.document_store.get(uri).version == 0

    changed = ctrl.snapshot_for_buffer(
        path=str(path),
        text="def g():\n    return 3\n",
        version=None,
    )
    assert changed is not None and changed.version == 1
    ctrl.notify_buffer_changed(changed)
    assert mgr.document_store.get(uri).text.endswith("return 3\n")

    ctrl.notify_buffer_closed(uri)
    assert mgr.document_store.get(uri) is None
    mgr.shutdown()


def test_path_to_file_uri_encodes_spaces(tmp_path: Path) -> None:
    path = tmp_path / "my file.py"
    path.write_text("x=1\n", encoding="utf-8")
    uri = path_to_file_uri(str(path))
    assert " " not in uri
    assert "%20" in uri or uri.endswith("my%20file.py")
