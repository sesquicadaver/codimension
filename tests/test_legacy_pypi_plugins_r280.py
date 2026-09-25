# -*- coding: utf-8 -*-
"""R280: drop legacy PyPI plugins without [Codimension] manifests."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Upstream wheel plugins install under site-packages/cdmplugins but ship only
# legacy [Core]/[Documentation] — R225 fail-closes them as third-party.
_LEGACY_PIP_PLUGINS = ("cdmgcplugin", "cdmsysinfoplugin")


def _runtime_requirement_text() -> str:
    chunks = [
        (ROOT / "pyproject.toml").read_text(encoding="utf-8"),
        (ROOT / "requirements-runtime.txt").read_text(encoding="utf-8"),
        (ROOT / "requirements.txt").read_text(encoding="utf-8"),
        (ROOT / "constraints.txt").read_text(encoding="utf-8"),
    ]
    return "\n".join(chunks).lower()


def test_r280_legacy_pypi_plugins_not_in_runtime_deps() -> None:
    """GC/sysinfo PyPI wheels must not be hard deps (no [Codimension] .cdmp)."""
    text = _runtime_requirement_text()
    for name in _LEGACY_PIP_PLUGINS:
        assert name.lower() not in text, f"{name} must not remain a runtime dependency"


def test_r280_in_tree_plugins_have_codimension_section() -> None:
    """Bundled fork plugins keep a complete [Codimension] block (R225)."""
    cdm_root = ROOT / "cdmplugins"
    cdmp_files = sorted(cdm_root.rglob("*.cdmp"))
    assert cdmp_files, "expected in-tree .cdmp plugins"
    for path in cdmp_files:
        body = path.read_text(encoding="utf-8")
        assert "[Codimension]" in body, f"{path.relative_to(ROOT)} missing [Codimension]"
