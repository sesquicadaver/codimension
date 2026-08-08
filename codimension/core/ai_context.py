# -*- coding: utf-8 -*-
#
# codimension - headless AI context packer (R151)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Pack SymbolIndex + CFG slice for a symbol into an AI-ready context (R151).

Pure / headless: no Qt, no network. Callers supply an in-memory
:class:`~core.symbol_index.SymbolIndex` and per-file source text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from core.cfg import CfgEdge, CfgGraph, CfgNode, CfgNodeKind, build_cfg_graph
from core.symbol_index import SymbolIndex, SymbolKind, SymbolRecord

AI_CONTEXT_FORMAT = "cdm-ai-context-v1"

_KIND_TO_CFG: dict[SymbolKind, CfgNodeKind] = {
    SymbolKind.FUNCTION: CfgNodeKind.FUNCTION,
    SymbolKind.METHOD: CfgNodeKind.FUNCTION,
    SymbolKind.CLASS: CfgNodeKind.CLASS,
}


@dataclass(frozen=True)
class CfgSlice:
    """Subset of a CFG rooted at a function/class scope node."""

    root_id: str
    nodes: tuple[CfgNode, ...]
    edges: tuple[CfgEdge, ...]

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly representation."""
        return {
            "root_id": self.root_id,
            "nodes": [
                {
                    "id": n.id,
                    "kind": n.kind.value,
                    "label": n.label,
                    "begin_line": n.begin_line,
                    "end_line": n.end_line,
                    "parent_id": n.parent_id,
                }
                for n in self.nodes
            ],
            "edges": [{"src": e.src, "dst": e.dst, "kind": e.kind.value, "label": e.label} for e in self.edges],
        }


@dataclass(frozen=True)
class AiContextPack:
    """Deterministic context bundle for one symbol (no network I/O)."""

    format: str
    symbol: SymbolRecord
    definitions: tuple[SymbolRecord, ...]
    references: tuple[SymbolRecord, ...]
    related: tuple[SymbolRecord, ...]
    cfg_slice: Optional[CfgSlice]
    source_excerpt: str
    excerpt_begin_line: int
    excerpt_end_line: int
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly pack for prompts / offline tooling."""

        def _sym(record: SymbolRecord) -> dict[str, Any]:
            return {
                "name": record.name,
                "kind": record.kind.value,
                "file": record.file,
                "qualname": record.qualname,
                "container": record.container,
                "line": record.line,
                "span": {"start": record.span.start, "end": record.span.end},
            }

        return {
            "format": self.format,
            "symbol": _sym(self.symbol),
            "definitions": [_sym(r) for r in self.definitions],
            "references": [_sym(r) for r in self.references],
            "related": [_sym(r) for r in self.related],
            "cfg_slice": self.cfg_slice.to_dict() if self.cfg_slice else None,
            "source_excerpt": self.source_excerpt,
            "excerpt_begin_line": self.excerpt_begin_line,
            "excerpt_end_line": self.excerpt_end_line,
            "notes": list(self.notes),
        }


def _find_scope_root(
    graph: CfgGraph,
    *,
    name: str,
    kind: SymbolKind,
    line: Optional[int],
) -> Optional[CfgNode]:
    """Pick the best CFG FUNCTION/CLASS node for ``name``."""
    want = _KIND_TO_CFG.get(kind)
    candidates = [
        n
        for n in graph.nodes.values()
        if n.label == name and (want is None or n.kind == want or n.kind in (CfgNodeKind.FUNCTION, CfgNodeKind.CLASS))
    ]
    if not candidates:
        candidates = [n for n in graph.nodes.values() if n.label == name]
    if not candidates:
        return None
    if line is not None:
        on_line = [n for n in candidates if n.begin_line <= line <= n.end_line]
        if on_line:
            candidates = on_line
    # Prefer narrower (innermost) scopes.
    candidates.sort(key=lambda n: (n.end_line - n.begin_line, n.begin_line, n.id))
    return candidates[0]


def _collect_subtree(graph: CfgGraph, root_id: str) -> set[str]:
    """Return ``root_id`` plus all nodes with ``parent_id`` in the subtree."""
    children: dict[Optional[str], list[str]] = {}
    for node in graph.nodes.values():
        children.setdefault(node.parent_id, []).append(node.id)
    out: set[str] = set()
    stack = [root_id]
    while stack:
        current = stack.pop()
        if current in out:
            continue
        out.add(current)
        stack.extend(children.get(current, ()))
    return out


def slice_cfg_for_symbol(
    graph: CfgGraph,
    *,
    name: str,
    kind: SymbolKind,
    line: Optional[int] = None,
) -> Optional[CfgSlice]:
    """Extract a CFG subtree for a named function/class scope."""
    root = _find_scope_root(graph, name=name, kind=kind, line=line)
    if root is None:
        return None
    ids = _collect_subtree(graph, root.id)
    nodes = tuple(graph.nodes[i] for i in sorted(ids) if i in graph.nodes)
    edges = tuple(e for e in graph.edges if e.src in ids and e.dst in ids)
    return CfgSlice(root_id=root.id, nodes=nodes, edges=edges)


def _excerpt_lines(source: str, begin_line: int, end_line: int, *, max_chars: int) -> tuple[str, int, int]:
    """Return a line-based excerpt clamped to ``max_chars``."""
    lines = source.splitlines(keepends=True)
    if not lines:
        return "", 1, 1
    start = max(1, begin_line)
    end = min(len(lines), max(start, end_line))
    chunk = "".join(lines[start - 1 : end])
    if len(chunk) > max_chars:
        chunk = chunk[:max_chars] + "\n# … truncated …\n"
    return chunk, start, end


def build_ai_context(
    index: SymbolIndex,
    name: str,
    source_by_file: Mapping[str, str],
    *,
    file: Optional[str] = None,
    kind: Optional[SymbolKind] = None,
    qualname: Optional[str] = None,
    max_excerpt_chars: int = 8_000,
) -> AiContextPack:
    """Build an :class:`AiContextPack` for ``name`` from index + sources.

    Raises ``ValueError`` when no defining symbol matches the filters.
    """
    definitions = index.find_definitions(name, file=file, kind=kind, qualname=qualname)
    if not definitions:
        raise ValueError(f"no definition found for symbol {name!r}")
    symbol = definitions[0]
    # References are project-wide (not limited to the defining file).
    references = index.find_references(name)
    related = tuple(
        r
        for r in index.by_container(symbol.qualname if symbol.kind is SymbolKind.CLASS else symbol.container)
        if r is not symbol and r.file == symbol.file
    )

    notes: list[str] = []
    cfg_slice: Optional[CfgSlice] = None
    source = source_by_file.get(symbol.file, "")
    begin_line = int(symbol.line or 1)
    end_line = begin_line

    if not source:
        notes.append(f"missing source for file {symbol.file!r}; CFG slice omitted")
    else:
        graph = build_cfg_graph(source)
        if graph.errors:
            notes.append(f"CFG parse reported {len(graph.errors)} error(s)")
        cfg_slice = slice_cfg_for_symbol(
            graph,
            name=symbol.name,
            kind=symbol.kind,
            line=symbol.line,
        )
        if cfg_slice is None:
            notes.append("no CFG scope node matched the symbol; excerpt uses symbol line only")
        else:
            root = next(n for n in cfg_slice.nodes if n.id == cfg_slice.root_id)
            begin_line = int(root.begin_line)
            end_line = int(root.end_line)

    excerpt, begin_line, end_line = _excerpt_lines(source, begin_line, end_line, max_chars=max_excerpt_chars)

    return AiContextPack(
        format=AI_CONTEXT_FORMAT,
        symbol=symbol,
        definitions=definitions,
        references=references,
        related=related,
        cfg_slice=cfg_slice,
        source_excerpt=excerpt,
        excerpt_begin_line=begin_line,
        excerpt_end_line=end_line,
        notes=tuple(notes),
    )


def build_ai_context_from_source(
    source: str,
    name: str,
    *,
    file: str = "<memory>",
    index: Optional[SymbolIndex] = None,
    kind: Optional[SymbolKind] = None,
    qualname: Optional[str] = None,
    max_excerpt_chars: int = 8_000,
) -> AiContextPack:
    """Convenience: single-file source; build a minimal index when omitted.

    When ``index`` is omitted, a lightweight :class:`SymbolIndex` is built from
    ``ast`` function/class defs only (no brief_ast / utils dependency).
    """
    if index is None:
        index = _index_from_ast(source, file)
    return build_ai_context(
        index,
        name,
        {file: source},
        file=file,
        kind=kind,
        qualname=qualname,
        max_excerpt_chars=max_excerpt_chars,
    )


def _index_from_ast(source: str, file: str) -> SymbolIndex:
    """Minimal SymbolIndex from stdlib ``ast`` (core-layer only)."""
    import ast

    from core.symbol_index import build_symbol

    tree = ast.parse(source)
    index = SymbolIndex()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            index.add(
                build_symbol(
                    node.name,
                    SymbolKind.FUNCTION,
                    file,
                    0,
                    0,
                    line=int(getattr(node, "lineno", 1) or 1),
                )
            )
        elif isinstance(node, ast.ClassDef):
            index.add(
                build_symbol(
                    node.name,
                    SymbolKind.CLASS,
                    file,
                    0,
                    0,
                    line=int(getattr(node, "lineno", 1) or 1),
                )
            )
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    index.add(
                        build_symbol(
                            child.name,
                            SymbolKind.METHOD,
                            file,
                            0,
                            0,
                            container=node.name,
                            line=int(getattr(child, "lineno", 1) or 1),
                        )
                    )
    # Spans left as 0,0 — CFG/line excerpt is the primary payload.
    return index


__all__ = [
    "AI_CONTEXT_FORMAT",
    "AiContextPack",
    "CfgSlice",
    "build_ai_context",
    "build_ai_context_from_source",
    "slice_cfg_for_symbol",
]
