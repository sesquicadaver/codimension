# -*- coding: utf-8 -*-
#
# codimension - debugger frame → CFG node mapping (R141)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Map debugger stack frames onto headless CFG nodes (R141).

Pure, Qt-free helpers. A CFG is per-file; callers build or supply a
:class:`~core.cfg.CfgGraph` for the frame's source file, then map by
line (and optional function name).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Sequence

from core.cfg import CfgGraph, CfgNode, CfgNodeKind, build_cfg_graph_from_file

_SYNTHETIC = frozenset(
    {
        CfgNodeKind.ENTRY,
        CfgNodeKind.EXIT,
        CfgNodeKind.JOIN,
        CfgNodeKind.MODULE,
    }
)


@dataclass(frozen=True)
class DebuggerFrame:
    """Minimal debugger stack frame used for CFG mapping."""

    file_name: str
    line: int
    func_name: str = ""
    frame_number: int = 0


@dataclass(frozen=True)
class FrameCfgMatch:
    """One ranked match of a frame to a CFG node."""

    frame: DebuggerFrame
    node: CfgNode
    score: int


def nodes_covering_line(graph: CfgGraph, line: int) -> tuple[CfgNode, ...]:
    """Return non-synthetic nodes whose line range covers ``line``."""
    if line < 1:
        return ()
    out: list[CfgNode] = []
    for node in graph.nodes.values():
        if node.kind in _SYNTHETIC:
            continue
        if node.begin_line <= line <= node.end_line:
            out.append(node)
    return tuple(out)


def _func_key(name: str) -> str:
    """Normalize a function name for comparison."""
    text = (name or "").strip()
    if text.startswith("<") and text.endswith(">"):
        return ""
    return text


def _ancestor_has_func(graph: CfgGraph, node: CfgNode, func_name: str) -> bool:
    """True if ``node`` or an ancestor is a FUNCTION/CLASS named ``func_name``."""
    current: Optional[CfgNode] = node
    seen: set[str] = set()
    while current is not None and current.id not in seen:
        seen.add(current.id)
        if current.kind in (CfgNodeKind.FUNCTION, CfgNodeKind.CLASS):
            if _func_key(current.label) == func_name:
                return True
        parent_id = current.parent_id
        current = graph.nodes.get(parent_id) if parent_id else None
    return False


def _score_node(graph: CfgGraph, node: CfgNode, frame: DebuggerFrame) -> int:
    """Higher score = better match for ``frame``."""
    # Prefer innermost (narrower) spans.
    span_lines = max(0, node.end_line - node.begin_line)
    score = max(0, 10_000 - span_lines)
    want = _func_key(frame.func_name)
    label = _func_key(node.label)
    is_scope = node.kind in (CfgNodeKind.FUNCTION, CfgNodeKind.CLASS)

    if want and is_scope and label == want and node.begin_line == frame.line:
        # Stopped on the ``def`` / ``class`` line itself.
        return 100_000 + score

    if is_scope:
        # Body stops should map to inner statements, not the enclosing scope node.
        score -= 20_000
    else:
        score += 100

    if want:
        if _ancestor_has_func(graph, node, want):
            score += 50_000
        elif label == want:
            score += 40_000
        elif label and (want in label or label in want):
            score += 5_000
    return score


def rank_frame_matches(graph: CfgGraph, frame: DebuggerFrame) -> tuple[FrameCfgMatch, ...]:
    """Rank all CFG nodes covering the frame line (best first)."""
    hits = nodes_covering_line(graph, frame.line)
    ranked = [FrameCfgMatch(frame=frame, node=n, score=_score_node(graph, n, frame)) for n in hits]
    ranked.sort(key=lambda m: (-m.score, m.node.begin_line, m.node.id))
    return tuple(ranked)


def map_frame_to_cfg_node(graph: CfgGraph, frame: DebuggerFrame) -> Optional[CfgNode]:
    """Return the best CFG node for ``frame``, or ``None`` if none cover the line."""
    matches = rank_frame_matches(graph, frame)
    return matches[0].node if matches else None


def map_stack_to_cfg(
    graph: CfgGraph,
    frames: Sequence[DebuggerFrame],
    *,
    file_name: Optional[str] = None,
) -> tuple[FrameCfgMatch, ...]:
    """Map each frame in ``frames`` that belongs to ``file_name`` (if given).

    When ``file_name`` is set, frames with a different path are skipped.
    Returns the best match per mapped frame (empty if no coverage).
    """
    want = os_path_norm(file_name) if file_name else None
    out: list[FrameCfgMatch] = []
    for frame in frames:
        if want is not None and os_path_norm(frame.file_name) != want:
            continue
        matches = rank_frame_matches(graph, frame)
        if matches:
            out.append(matches[0])
    return tuple(out)


def map_frame_from_source_file(frame: DebuggerFrame) -> Optional[CfgNode]:
    """Build a CFG from ``frame.file_name`` and map the frame (file must exist)."""
    path = frame.file_name
    if not path or not os.path.isfile(path):
        return None
    try:
        graph = build_cfg_graph_from_file(path)
    except OSError:
        return None
    except Exception:
        # Parser/runtime failures must not break the debugger UI.
        return None
    if graph.errors:
        return None
    return map_frame_to_cfg_node(graph, frame)


def os_path_norm(path: Optional[str]) -> str:
    """Normalize a filesystem path for frame/file comparisons."""
    if not path:
        return ""
    return os.path.normcase(os.path.normpath(path))


def frame_from_stack_item(item: Sequence[object], frame_number: int = 0) -> DebuggerFrame:
    """Build a :class:`DebuggerFrame` from a debugger stack tuple.

    Expected shape: ``(fileName, line, [funcName, [funcArgs]])``.
    """
    file_name = str(item[0]) if item else ""
    line = int(item[1]) if len(item) > 1 else 0
    func_name = str(item[2]) if len(item) >= 3 else ""
    if func_name.startswith("<"):
        func_name = ""
    return DebuggerFrame(
        file_name=file_name,
        line=line,
        func_name=func_name,
        frame_number=frame_number,
    )
