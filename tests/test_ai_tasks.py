# -*- coding: utf-8 -*-
"""AI analysis tasks, docstring apply, and project-scoped module context."""

from __future__ import annotations

from pathlib import Path

import pytest
from core.ai_docstring import apply_google_docstring
from core.ai_project_context import (
    assert_path_in_project,
    build_project_module_context,
    extract_import_modules,
)
from core.ai_tasks import (
    AiTaskKind,
    AiTaskRequest,
    execute_ai_task,
    list_project_py_files,
)
from core.ai_ui import AiBackendConfigError, resolve_default_backend


def test_list_project_py_files(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x=1\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("nope\n", encoding="utf-8")
    sub = tmp_path / "pkg"
    sub.mkdir()
    (sub / "c.py").write_text("y=2\n", encoding="utf-8")
    files = {
        str(tmp_path / "a.py"),
        str(tmp_path / "b.txt"),
        str(sub / "c.py"),
        str(sub) + "/",
    }
    out = list_project_py_files(files, str(tmp_path))
    assert str(tmp_path / "a.py") in out
    assert str(sub / "c.py") in out
    assert all(p.endswith(".py") for p in out)


def test_module_analysis_requires_project_context() -> None:
    def complete(system: str, user: str) -> str:
        return "should not run"

    with pytest.raises(ValueError, match="project context"):
        execute_ai_task(
            AiTaskRequest(
                kind=AiTaskKind.ANALYZE_MODULE,
                title="m",
                file_path="m.py",
                source="def f(x):\n    return x\n",
            ),
            complete,
            backend_name="fake",
        )


def test_execute_module_uses_project_neighbours(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    helper = pkg / "helper.py"
    helper.write_text("def help_me(x):\n    return x + 1\n", encoding="utf-8")
    main = pkg / "main.py"
    main.write_text("from pkg.helper import help_me\n\ndef run():\n    return help_me(1)\n", encoding="utf-8")
    files = (str(helper), str(main))
    captured: list[str] = []

    def complete(system: str, user: str) -> str:
        captured.append(user)
        assert "Project context" in user
        assert "pkg/helper.py" in user.replace("\\", "/") or "pkg\\helper.py" in user
        assert "help_me" in user
        assert "within the open Codimension project" in user
        return "## Analysis\nOK in project"

    result = execute_ai_task(
        AiTaskRequest(
            kind=AiTaskKind.ANALYZE_MODULE,
            title="main",
            file_path=str(main),
            source=main.read_text(encoding="utf-8"),
            project_dir=str(tmp_path),
            project_files=files,
        ),
        complete,
        backend_name="fake",
    )
    assert "OK in project" in result.text
    assert captured


def test_assert_path_rejects_outside_project(tmp_path: Path) -> None:
    inside = tmp_path / "in.py"
    inside.write_text("x=1\n", encoding="utf-8")
    outside = tmp_path.parent / "out.py"
    outside.write_text("y=2\n", encoding="utf-8")
    files = (str(inside),)
    assert assert_path_in_project(str(inside), str(tmp_path), files) == str(inside.resolve())
    with pytest.raises(ValueError, match="outside"):
        assert_path_in_project(str(outside), str(tmp_path), files)


def test_extract_imports_and_context_block(tmp_path: Path) -> None:
    mod = tmp_path / "a.py"
    other = tmp_path / "b.py"
    other.write_text("def b_fn():\n    return 1\n", encoding="utf-8")
    mod.write_text("import os\nfrom b import b_fn\n\ndef a_fn():\n    return b_fn()\n", encoding="utf-8")
    names = extract_import_modules(mod.read_text(encoding="utf-8"))
    assert "os" in names
    assert "b" in names
    ctx = build_project_module_context(
        module_path=str(mod),
        source=mod.read_text(encoding="utf-8"),
        project_dir=str(tmp_path),
        project_files=(str(mod), str(other)),
    )
    block = ctx.to_prompt_block()
    assert "Project root:" in block
    assert any("b" in item for item in ctx.local_imports)
    assert "os" in ctx.external_imports


def test_execute_docstring_with_fake_complete() -> None:
    captured: list[str] = []

    def complete(system: str, user: str) -> str:
        captured.append(user)
        assert "Selected fragment" in user
        assert "def f(x):" in user
        assert "Supporting context" in user
        if "Google-style" in system or "docstring" in system.lower():
            return "Args:\n    x: value\n\nReturns:\n    int"
        return "nope"

    doc = execute_ai_task(
        AiTaskRequest(
            kind=AiTaskKind.DOCSTRING,
            title="d",
            file_path="m.py",
            source="def f(x):\n    return x\n",
            symbol_name="f",
        ),
        complete,
        backend_name="fake",
    )
    assert "Args:" in doc.text
    assert captured


def test_docstring_uses_selection_not_cfg_noise() -> None:
    """Selection is authoritative; prompt must not ship CFG/ref metadata noise."""
    source = (
        "import os\n"
        "from helper import nudge\n\n"
        "class Box:\n"
        "    def paint(self, color):\n"
        "        path = os.path.join('a', color)\n"
        "        return nudge(path)\n"
    )
    selection = "    def paint(self, color):\n        path = os.path.join('a', color)\n        return nudge(path)\n"
    captured: list[tuple[str, str]] = []

    def complete(system: str, user: str) -> str:
        captured.append((system, user))
        assert "Selected fragment" in user
        assert "def paint" in user
        assert "nudge(path)" in user
        assert "Module imports" in user or "import os" in user
        assert "Definitions:" not in user
        assert "cfg_slice" not in user.lower()
        assert "Selected fragment is authoritative" in system
        return "Paint the box.\n\nArgs:\n    color: color name"

    result = execute_ai_task(
        AiTaskRequest(
            kind=AiTaskKind.DOCSTRING,
            title="d",
            file_path="box.py",
            source=source,
            symbol_name="paint",
            selected_text=selection,
            cursor_line=5,
        ),
        complete,
        backend_name="fake",
    )
    assert result.symbol_name == "paint"
    assert "Paint" in result.text
    assert captured


def test_resolve_docstring_fragment_qt_newlines() -> None:
    from core.ai_docstring_context import normalize_editor_selection, resolve_docstring_fragment

    qt_sel = "def g():\u2029    return 1\u2029"
    assert "\n" in normalize_editor_selection(qt_sel)
    frag, name = resolve_docstring_fragment(
        "def g():\n    return 1\n",
        selected_text=qt_sel,
        symbol_name="",
        cursor_line=1,
    )
    assert name == "g"
    assert "return 1" in frag


def test_apply_google_docstring_insert_and_replace() -> None:
    src = "def f(x):\n    return x\n"
    out = apply_google_docstring(src, "f", "Return x.\n\nArgs:\n    x: value")
    assert '"""' in out
    assert "Return x." in out
    out2 = apply_google_docstring(out, "f", "Updated.")
    assert out2.count('"""') == 2
    assert "Updated." in out2


def test_require_live_rejects_offline(tmp_path: Path) -> None:
    with pytest.raises(AiBackendConfigError):
        resolve_default_backend(home=str(tmp_path), require_live=True)
