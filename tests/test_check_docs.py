# -*- coding: utf-8 -*-
"""Unit tests for scripts/check_docs.py (B11 docs gate)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_docs.py"


def _load_check_docs():
    """Load check_docs module without requiring package install."""
    spec = importlib.util.spec_from_file_location("check_docs", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_docs"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def check_docs():
    return _load_check_docs()


def test_parse_ci_python_matrix(check_docs):
    text = 'python-version: ["3.10", "3.11", "3.12", "3.13"]\npython-version: "3.12"\n'
    assert check_docs.parse_ci_python_matrix(text) == ["3.10", "3.11", "3.12", "3.13"]


def test_format_ci_range(check_docs):
    assert check_docs.format_ci_range(["3.10", "3.11", "3.12", "3.13"]) == "3.10–3.13"


def test_audit_id_statuses_open_closed(check_docs):
    table = """
| ID | Status |
|----|--------|
| B11 | ✅ done |
| B09 / B10 | 🔓 OPEN |
| D08 | OPEN |
"""
    assert check_docs.audit_id_statuses(table) == {
        "B11": "CLOSED",
        "B09": "OPEN",
        "B10": "OPEN",
        "D08": "OPEN",
    }


def test_heading_slugs_and_anchors(check_docs):
    md = "# Hello World\n\n## Second {#custom}\n"
    slugs = check_docs.heading_slugs(md)
    assert "hello-world" in slugs
    assert "custom" in slugs


def test_fenced_example_links_ignored(check_docs, tmp_path):
    """Pedagogical image paths inside fences must not fail the gate."""
    root = tmp_path
    (root / "doc").mkdir()
    md = root / "doc" / "sample.md"
    md.write_text(
        "# Title\n\n```markdown\n![x](missing.png)\n```\n\nSee [ok](./other.md).\n",
        encoding="utf-8",
    )
    (root / "doc" / "other.md").write_text("# Other\n", encoding="utf-8")
    errors = check_docs.check_links(root, [md])
    assert errors == []


def test_image_and_extensionless_links(check_docs, tmp_path):
    root = tmp_path
    (root / "doc").mkdir()
    (root / "LICENSE").write_text("gpl\n", encoding="utf-8")
    (root / "doc" / "pic.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    md = root / "doc" / "a.md"
    md.write_text(
        "# A\n\n![p](pic.png)\n\n[lic](../LICENSE)\n[bad](nope.png)\n",
        encoding="utf-8",
    )
    errors = check_docs.check_links(root, [md])
    assert any("nope.png" in e for e in errors)
    assert not any("LICENSE" in e for e in errors)
    assert not any("pic.png" in e for e in errors)


def test_repo_docs_check_passes(check_docs):
    """Full-tree gate on the repository must stay green."""
    files = check_docs.iter_markdown_files(ROOT)
    errors = (
        check_docs.check_links(ROOT, files)
        + check_docs.check_invariants(ROOT)
        + check_docs.check_python_matrix(ROOT)
        + check_docs.check_bilingual_and_audit(ROOT)
    )
    assert errors == [], errors
