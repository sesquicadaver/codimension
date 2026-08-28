# -*- coding: utf-8 -*-
"""R196: utils.versions stays free of ui/Qt imports."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from codimension.utils.versions import getQtVersion

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "scripts" / "check_module_boundaries.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("check_module_boundaries", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_get_qt_version_without_injection() -> None:
    """Missing UI injection must not import ui; returns n/a."""
    assert getQtVersion() == "n/a"
    assert getQtVersion(None) == "n/a"


def test_get_qt_version_injected() -> None:
    """UI layer can supply QT_VERSION_STR without utils importing ui."""
    assert getQtVersion("5.15.2") == "5.15.2"


def test_get_component_info_qt_row_injected(monkeypatch) -> None:
    """About table Qt row uses the injected version string."""
    import codimension.utils.versions as versions

    monkeypatch.setattr(versions, "getCodimensionVersion", lambda: ("0.0-test", "/tmp/x"))
    monkeypatch.setattr(versions, "getPackageVersionAndLocation", lambda _n: ("1.0", None))
    monkeypatch.setattr(versions, "getPythonInterpreterVersion", lambda: ("3.12.0", "/usr/bin/python"))
    monkeypatch.setattr(versions, "getGraphvizVersion", lambda: ("n/a", None))
    monkeypatch.setattr(versions, "getJavaVersion", lambda: ("n/a", None))
    monkeypatch.setattr(versions, "getPlantUMLVersion", lambda: ("n/a", None))

    components = versions.getComponentInfo(qt_version="9.9.9-test")
    qt_rows = [row for row in components if row[0] == "Qt"]
    assert len(qt_rows) == 1
    assert qt_rows[0][1] == "9.9.9-test"


def test_versions_module_removed_from_legacy_allowlist() -> None:
    """R196 shrinks UTILS_LEGACY_EDGES by dropping versions.py."""
    gate = _load_gate()
    path = _ROOT / "codimension" / "utils" / "versions.py"
    failures = gate.check_file(path)
    assert failures == []
    assert "codimension/utils/versions.py" not in gate.UTILS_LEGACY_EDGES
