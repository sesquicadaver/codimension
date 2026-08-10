# -*- coding: utf-8 -*-
"""AI analysis tasks, docstring apply, and project file listing."""

from __future__ import annotations

from pathlib import Path

import pytest
from core.ai_docstring import apply_google_docstring
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


def test_execute_module_and_docstring_with_fake_complete() -> None:
    calls: list[tuple[str, str]] = []

    def complete(system: str, user: str) -> str:
        calls.append((system, user))
        if "docstring" in system.lower() or "Google-style" in system:
            return "Args:\n    x: value\n\nReturns:\n    int"
        return "## Analysis\nOK"

    mod = execute_ai_task(
        AiTaskRequest(
            kind=AiTaskKind.ANALYZE_MODULE,
            title="m",
            file_path="m.py",
            source="def f(x):\n    return x\n",
        ),
        complete,
        backend_name="fake",
    )
    assert "OK" in mod.text
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
    assert len(calls) >= 2


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
