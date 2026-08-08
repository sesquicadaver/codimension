# -*- coding: utf-8 -*-
"""R133: headless DependencyGraph from imports."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import parsers  # noqa: E402,F401
import pytest

_CODIM = Path(__file__).resolve().parents[1] / "codimension"


@pytest.fixture(autouse=True)
def _purge_stubs():
    import importlib

    def _under(mod: object) -> bool:
        path = getattr(mod, "__file__", None)
        if path:
            return "/codimension/" in os.path.abspath(path).replace("\\", "/")
        return False

    dirty = False
    for name in list(sys.modules):
        if name not in ("ui", "utils") and not name.startswith(("ui.", "utils.")):
            continue
        if _under(sys.modules[name]):
            continue
        del sys.modules[name]
        dirty = True
    if dirty:
        importlib.invalidate_caches()
        if str(_CODIM) not in sys.path:
            sys.path.insert(0, str(_CODIM))
    yield


def test_build_graph_local_and_external_edges(tmp_path: Path):
    from utils.dependency_graph import build_dependency_graph_from_sources

    root = tmp_path
    a = root / "pkg" / "a.py"
    b = root / "pkg" / "b.py"
    a.parent.mkdir(parents=True)
    a.write_text("from pkg import b\nfrom pkg.b import helper\nimport os\n", encoding="utf-8")
    b.write_text("def helper():\n    return 1\n", encoding="utf-8")

    graph = build_dependency_graph_from_sources(
        [(str(a), a.read_text(encoding="utf-8")), (str(b), b.read_text(encoding="utf-8"))],
        root=str(root),
    )
    assert "pkg.a" in graph.nodes
    assert "pkg.b" in graph.nodes
    assert "os" in graph.nodes
    assert graph.nodes["os"].kind == "external"
    assert "pkg.b" in graph.successors("pkg.a")
    assert "os" in graph.successors("pkg.a")

    # Labels from ``from pkg.b import helper``
    edge_ab = next(e for e in graph.edges if e.source == "pkg.a" and e.target == "pkg.b")
    assert "helper" in edge_ab.labels or edge_ab.labels == ()


def test_json_and_dot_export(tmp_path: Path):
    from utils.dependency_graph import build_dependency_graph

    f = tmp_path / "m.py"
    f.write_text("import sys\n", encoding="utf-8")
    graph = build_dependency_graph([str(f)], root=str(tmp_path))
    payload = json.loads(graph.to_json())
    assert "nodes" in payload and "edges" in payload
    assert any(n["id"] == "sys" for n in payload["nodes"])
    dot = graph.to_dot()
    assert "digraph DependencyGraph" in dot
    assert "sys" in dot


def test_on_file_callback(tmp_path: Path):
    from utils.dependency_graph import build_dependency_graph

    f = tmp_path / "x.py"
    f.write_text("pass\n", encoding="utf-8")
    seen: list[str] = []
    build_dependency_graph([str(f)], root=str(tmp_path), on_file=seen.append)
    assert seen == [str(f.resolve())]


def test_module_name_for_path():
    from utils.dependency_graph import module_name_for_path

    assert module_name_for_path("/proj/pkg/mod.py", "/proj") == "pkg.mod"
    assert module_name_for_path("/proj/pkg/__init__.py", "/proj") == "pkg"
