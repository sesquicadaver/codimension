# -*- coding: utf-8 -*-
"""R218 — versioned AI docstring target + post-patch validation."""

from __future__ import annotations

import ast

import pytest
from core.ai_docstring import (
    apply_google_docstring,
    build_docstring_target,
    document_version_of,
)
from core.ai_tasks import AiTaskKind, AiTaskRequest, execute_ai_task


def test_ambiguous_name_requires_qualname() -> None:
    src = (
        "class First:\n"
        "    def close(self):\n"
        "        return 1\n"
        "\n"
        "class Second:\n"
        "    def close(self):\n"
        "        return 2\n"
    )
    with pytest.raises(ValueError, match="ambiguous"):
        apply_google_docstring(src, "close", "Close resource.")

    target = build_docstring_target(src, symbol_name="close", qualname="Second.close")
    assert target.qualname == "Second.close"
    out = apply_google_docstring(
        src,
        "close",
        "Close Second.",
        target=target,
    )
    tree = ast.parse(out)
    second = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Second")
    method = second.body[0]
    assert isinstance(method, ast.FunctionDef)
    assert ast.get_docstring(method) == "Close Second."
    first = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "First")
    assert ast.get_docstring(first.body[0]) is None


def test_same_line_suite_insert_is_valid() -> None:
    src = "def f(): pass\n"
    out = apply_google_docstring(src, "f", "Trivial helper.")
    ast.parse(out)
    assert '"""Trivial helper."""' in out
    assert out.index("def f():") < out.index('"""Trivial helper."""')
    assert "pass" in out


def test_stale_document_version_rejected() -> None:
    src = "def f(x):\n    return x\n"
    target = build_docstring_target(src, file_path="/tmp/m.py", symbol_name="f")
    assert target.document_version == document_version_of(src)
    changed = "def f(x):\n    return x + 1\n"
    with pytest.raises(ValueError, match="document changed"):
        apply_google_docstring(
            changed,
            "f",
            "Return x+1.",
            target=target,
            require_version_match=True,
        )


def test_dual_quote_body_rejected() -> None:
    src = "def f():\n    return 1\n"
    with pytest.raises(ValueError, match="both"):
        apply_google_docstring(src, "f", "has \"\"\" and ''' both")


def test_execute_docstring_attaches_versioned_target() -> None:
    source = "class Box:\n    def paint(self, color):\n        return color\n"

    def complete(_system: str, _user: str) -> str:
        return "Paint the box.\n\nArgs:\n    color: name"

    result = execute_ai_task(
        AiTaskRequest(
            kind=AiTaskKind.DOCSTRING,
            title="d",
            file_path="/proj/box.py",
            source=source,
            symbol_name="paint",
            cursor_line=2,
        ),
        complete,
        backend_name="fake",
    )
    assert result.docstring_target is not None
    assert result.docstring_target.qualname == "Box.paint"
    assert result.docstring_target.file_path == "/proj/box.py"
    assert result.docstring_target.document_version == document_version_of(source)
    out = apply_google_docstring(
        source,
        result.symbol_name,
        result.text,
        target=result.docstring_target,
    )
    method = ast.parse(out).body[0].body[0]
    assert isinstance(method, ast.FunctionDef)
    assert ast.get_docstring(method) is not None
    assert "Paint the box." in (ast.get_docstring(method) or "")
