# -*- coding: utf-8 -*-
"""T080–T082: headless core/infrastructure APIs without Qt."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_t080_syntax_parse_subprocess_without_qt() -> None:
    """Gate: python -c parse via core.syntax must not need Qt."""
    root = Path(__file__).resolve().parents[1]
    code = (
        "import sys\n"
        f"sys.path.insert(0, {str(root)!r})\n"
        "assert 'PyQt5' not in sys.modules\n"
        "from codimension.core.syntax import parse_brief_from_memory\n"
        "info = parse_brief_from_memory('def f():\\n    return 1\\n')\n"
        "assert info is not None\n"
        "assert 'PyQt5' not in sys.modules\n"
        "print('OK')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(root),
        env={**dict(**{k: v for k, v in __import__("os").environ.items() if k != "QT_API"})},
    )
    assert proc.returncode == 0, proc.stderr
    assert "OK" in proc.stdout


def test_t081_flow_parse_subprocess_without_qt() -> None:
    """Gate: core.flow parse must not import Qt."""
    root = Path(__file__).resolve().parents[1]
    code = (
        "import sys\n"
        f"sys.path.insert(0, {str(root)!r})\n"
        "from codimension.core.flow import parse_control_flow_from_memory\n"
        "cf = parse_control_flow_from_memory('x = 1\\n')\n"
        "assert cf is not None\n"
        "assert 'PyQt5' not in sys.modules\n"
        "print('OK')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(root),
    )
    assert proc.returncode == 0, proc.stderr
    assert "OK" in proc.stdout


def test_t082_process_environ_override() -> None:
    from codimension.infrastructure.process import build_tool_environ

    env = build_tool_environ(overrides={"FOO": "bar"}, base={"PATH": "/bin"})
    assert env["FOO"] == "bar"
    assert env["PYTHONIOENCODING"] == "utf-8"
    assert env["PATH"] == "/bin"
