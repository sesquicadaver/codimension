# -*- coding: utf-8 -*-
"""R141: debugger frames map onto CFG nodes."""

from __future__ import annotations

from pathlib import Path

from core.cfg import CfgNodeKind, build_cfg_graph
from core.cfg_frames import (
    DebuggerFrame,
    frame_from_stack_item,
    map_frame_from_source_file,
    map_frame_to_cfg_node,
    map_stack_to_cfg,
    nodes_covering_line,
    rank_frame_matches,
)


def test_map_frame_prefers_innermost_and_func() -> None:
    source = (
        "def outer():\n    def inner(x):\n        if x:\n            return 1\n        return 0\n    return inner(1)\n"
    )
    graph = build_cfg_graph(source)
    # Line 4 is `return 1` inside if inside inner
    frame = DebuggerFrame(file_name="buf.py", line=4, func_name="inner")
    node = map_frame_to_cfg_node(graph, frame)
    assert node is not None
    assert node.kind == CfgNodeKind.RETURN
    ranked = rank_frame_matches(graph, frame)
    assert ranked[0].node.id == node.id


def test_map_frame_function_header() -> None:
    graph = build_cfg_graph("def f(x):\n    return x\n")
    frame = DebuggerFrame(file_name="t.py", line=1, func_name="f")
    node = map_frame_to_cfg_node(graph, frame)
    assert node is not None
    assert node.kind == CfgNodeKind.FUNCTION
    assert node.label == "f"


def test_nodes_covering_line_skips_synthetic() -> None:
    graph = build_cfg_graph("x = 1\n")
    hits = nodes_covering_line(graph, 1)
    kinds = {n.kind for n in hits}
    assert CfgNodeKind.ENTRY not in kinds
    assert CfgNodeKind.EXIT not in kinds
    assert CfgNodeKind.MODULE not in kinds
    assert hits


def test_map_stack_filters_by_file() -> None:
    graph = build_cfg_graph("def g():\n    y = 2\n")
    frames = [
        DebuggerFrame("/other.py", 1, "g", 0),
        DebuggerFrame("/proj/a.py", 2, "g", 1),
    ]
    hits = map_stack_to_cfg(graph, frames, file_name="/proj/a.py")
    assert len(hits) == 1
    assert hits[0].frame.frame_number == 1
    assert hits[0].node.kind in (CfgNodeKind.CODE, CfgNodeKind.FUNCTION)


def test_frame_from_stack_item() -> None:
    frame = frame_from_stack_item(("/tmp/x.py", 12, "foo", "a=1"), frame_number=3)
    assert frame.file_name.endswith("x.py")
    assert frame.line == 12
    assert frame.func_name == "foo"
    assert frame.frame_number == 3
    # Angle-bracket names cleared (like StackViewer)
    frame2 = frame_from_stack_item(("/tmp/x.py", 1, "<module>"), 0)
    assert frame2.func_name == ""


def test_map_frame_from_source_file(tmp_path: Path) -> None:
    path = tmp_path / "sample.py"
    path.write_text("def f():\n    return 42\n", encoding="utf-8")
    frame = DebuggerFrame(file_name=str(path), line=2, func_name="f")
    node = map_frame_from_source_file(frame)
    assert node is not None
    assert node.kind == CfgNodeKind.RETURN


def test_map_missing_file_returns_none() -> None:
    frame = DebuggerFrame(file_name="/no/such/file_r141.py", line=1, func_name="f")
    assert map_frame_from_source_file(frame) is None
