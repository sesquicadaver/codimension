# -*- coding: utf-8 -*-
"""R103/R195: named-layer module boundary matrix gate."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "scripts" / "check_module_boundaries.py"
_INVENTORY = _ROOT / "doc" / "technology" / "utils-side-effect-inventory.md"
_INVENTORY_UK = _ROOT / "doc" / "uk" / "technology" / "utils-side-effect-inventory.md"


def _load():
    spec = importlib.util.spec_from_file_location("check_module_boundaries", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_r103_matrix_covers_named_layers() -> None:
    """Every named layer has an ALLOWED_EDGES entry."""
    gate = _load()
    assert set(gate.ALLOWED_EDGES) == set(gate.NAMED_LAYERS)


def test_r103_core_cannot_import_utils() -> None:
    """core → utils is illegal under the enforced matrix."""
    gate = _load()
    assert "utils" not in gate.ALLOWED_EDGES["core"]
    assert "ui" not in gate.ALLOWED_EDGES["app"]
    assert "plugins" not in gate.ALLOWED_EDGES["infrastructure"]


def test_r195_utils_floor_excludes_ui_plugins() -> None:
    """R195: utils open floor no longer includes ui/plugins."""
    gate = _load()
    assert gate.ALLOWED_EDGES["utils"] == frozenset({"core", "infrastructure", "app"})
    assert "ui" not in gate.ALLOWED_EDGES["utils"]
    assert "plugins" not in gate.ALLOWED_EDGES["utils"]
    assert gate.UTILS_LEGACY_EDGES, "legacy map must list current hotspots"


def test_r103_flags_illegal_edge(tmp_path: Path) -> None:
    """Injecting core → ui must fail the file check."""
    gate = _load()
    core_dir = _ROOT / "codimension" / "core"
    evil = core_dir / "_r103_boundary_probe.py"
    try:
        evil.write_text("from ui.qt import QApplication\n", encoding="utf-8")
        failures = gate.check_file(evil)
        assert failures, "core → ui/qt must be rejected"
        assert any("illegal edge core →" in f for f in failures)
    finally:
        if evil.exists():
            evil.unlink()


def test_r195_new_utils_ui_edge_rejected() -> None:
    """A non-allowlisted utils module must not import ui."""
    gate = _load()
    utils_dir = _ROOT / "codimension" / "utils"
    evil = utils_dir / "_r195_boundary_probe.py"
    try:
        evil.write_text("from ui.qt import QObject\n", encoding="utf-8")
        failures = gate.check_file(evil)
        assert failures, "new utils → ui must be rejected"
        assert any("illegal edge utils → ui" in f for f in failures)
    finally:
        if evil.exists():
            evil.unlink()


def test_r195_inventory_documents_legacy_modules() -> None:
    """Inventory markdown lists every grandfathered utils path basename."""
    gate = _load()
    assert _INVENTORY.is_file()
    assert _INVENTORY_UK.is_file()
    text = _INVENTORY.read_text(encoding="utf-8")
    for rel in gate.UTILS_LEGACY_EDGES:
        basename = Path(rel).name
        assert basename in text, f"inventory missing {basename}"


def test_r103_repo_is_green() -> None:
    """Current tree satisfies the enforced boundary floor."""
    gate = _load()
    assert gate.main() == 0
