# -*- coding: utf-8 -*-
#
# codimension - headless CFG graph model (R140.a)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Headless CFG graph model separated from ``flowui`` canvas (R140.a).

Builds an immutable-ish node/edge graph from a control-flow fragment tree
(``core.flow`` / ``cdmcfparser``). Canvas consumption is deferred to R140.b.

Spans are half-open Unicode character ranges ``[start, end)`` via
:class:`core.symbol_index.SourceSpan`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from core.symbol_index import SourceSpan

# Fragment kind constants — keep in sync with ``parsers.flow_ast``.
_CODEBLOCK = 6
_FUNCTION = 7
_CLASS = 8
_BREAK = 9
_CONTINUE = 10
_RETURN = 11
_RAISE = 12
_ASSERT = 13
_SYSEXIT = 14
_WHILE = 15
_FOR = 16
_IMPORT = 17
_ELIF_PART = 18
_IF = 19
_WITH = 20
_EXCEPT_PART = 21
_TRY = 22
_MATCH = 25
_CASE_PART = 26
_TRY_STAR = 27
_CONTROL_FLOW = 64


class CfgNodeKind(str, Enum):
    """Stable CFG node kinds for headless consumers."""

    MODULE = "module"
    ENTRY = "entry"
    EXIT = "exit"
    CODE = "code"
    FUNCTION = "function"
    CLASS = "class"
    IF = "if"
    BRANCH = "branch"
    LOOP = "loop"
    TRY = "try"
    WITH = "with"
    MATCH = "match"
    RETURN = "return"
    RAISE = "raise"
    BREAK = "break"
    CONTINUE = "continue"
    ASSERT = "assert"
    SYSEXIT = "sysexit"
    IMPORT = "import"
    JOIN = "join"


class CfgEdgeKind(str, Enum):
    """Directed edge semantics between CFG nodes."""

    NEXT = "next"
    TRUE = "true"
    FALSE = "false"
    BODY = "body"
    LOOP_BACK = "loop_back"
    ELSE = "else"
    EXCEPT = "except"
    FINALLY = "finally"
    CASE = "case"
    EXIT = "exit"


_FRAG_TO_KIND: dict[int, CfgNodeKind] = {
    _CODEBLOCK: CfgNodeKind.CODE,
    _FUNCTION: CfgNodeKind.FUNCTION,
    _CLASS: CfgNodeKind.CLASS,
    _BREAK: CfgNodeKind.BREAK,
    _CONTINUE: CfgNodeKind.CONTINUE,
    _RETURN: CfgNodeKind.RETURN,
    _RAISE: CfgNodeKind.RAISE,
    _ASSERT: CfgNodeKind.ASSERT,
    _SYSEXIT: CfgNodeKind.SYSEXIT,
    _WHILE: CfgNodeKind.LOOP,
    _FOR: CfgNodeKind.LOOP,
    _IMPORT: CfgNodeKind.IMPORT,
    _ELIF_PART: CfgNodeKind.BRANCH,
    _IF: CfgNodeKind.IF,
    _WITH: CfgNodeKind.WITH,
    _EXCEPT_PART: CfgNodeKind.BRANCH,
    _TRY: CfgNodeKind.TRY,
    _TRY_STAR: CfgNodeKind.TRY,
    _MATCH: CfgNodeKind.MATCH,
    _CASE_PART: CfgNodeKind.BRANCH,
    _CONTROL_FLOW: CfgNodeKind.MODULE,
}

_TERMINAL_KINDS = frozenset(
    {
        CfgNodeKind.RETURN,
        CfgNodeKind.RAISE,
        CfgNodeKind.BREAK,
        CfgNodeKind.CONTINUE,
        CfgNodeKind.SYSEXIT,
    }
)


@dataclass(frozen=True, slots=True)
class CfgNode:
    """One CFG node with a half-open source span."""

    id: str
    kind: CfgNodeKind
    span: SourceSpan
    begin_line: int = 1
    end_line: int = 1
    label: str = ""
    frag_kind: Optional[int] = None
    parent_id: Optional[str] = None


@dataclass(frozen=True, slots=True)
class CfgEdge:
    """Directed CFG edge ``src -> dst``."""

    src: str
    dst: str
    kind: CfgEdgeKind
    label: str = ""


@dataclass
class CfgGraph:
    """In-memory CFG with entry/exit anchors."""

    nodes: dict[str, CfgNode] = field(default_factory=dict)
    edges: list[CfgEdge] = field(default_factory=list)
    entry_id: str = ""
    exit_id: str = ""
    errors: tuple[tuple[int, int, str], ...] = ()

    def successors(self, node_id: str, *, kind: Optional[CfgEdgeKind] = None) -> tuple[str, ...]:
        """Return destination ids of edges leaving ``node_id``."""
        out: list[str] = []
        for edge in self.edges:
            if edge.src != node_id:
                continue
            if kind is not None and edge.kind != kind:
                continue
            out.append(edge.dst)
        return tuple(out)

    def predecessors(self, node_id: str) -> tuple[str, ...]:
        """Return source ids of edges entering ``node_id``."""
        return tuple(e.src for e in self.edges if e.dst == node_id)

    def nodes_of_kind(self, kind: CfgNodeKind) -> tuple[CfgNode, ...]:
        """Return nodes matching ``kind`` in insertion order."""
        return tuple(n for n in self.nodes.values() if n.kind == kind)


class _Builder:
    """Mutable builder that walks a CF fragment tree into a CfgGraph."""

    def __init__(self) -> None:
        self.graph = CfgGraph()
        self._seq = 0

    def new_id(self, prefix: str) -> str:
        """Allocate a unique node id."""
        self._seq += 1
        return f"{prefix}_{self._seq}"

    def add_node(
        self,
        kind: CfgNodeKind,
        frag: Any = None,
        *,
        label: str = "",
        parent_id: Optional[str] = None,
        span: Optional[SourceSpan] = None,
        prefix: Optional[str] = None,
    ) -> str:
        """Insert a node and return its id."""
        node_id = self.new_id(prefix or kind.value)
        if span is None:
            span = _span_of(frag) if frag is not None else SourceSpan(0, 0)
        begin_line, end_line = (1, 1)
        if frag is not None and hasattr(frag, "getLineRange"):
            begin_line, end_line = frag.getLineRange()
        if not label and frag is not None and hasattr(frag, "getDisplayValue"):
            try:
                label = str(frag.getDisplayValue() or "")
            except Exception:
                label = ""
        if not label and frag is not None and getattr(frag, "name", None):
            label = str(frag.name)
        frag_kind = int(getattr(frag, "kind", 0) or 0) if frag is not None else None
        self.graph.nodes[node_id] = CfgNode(
            id=node_id,
            kind=kind,
            span=span,
            begin_line=int(begin_line),
            end_line=int(end_line),
            label=label,
            frag_kind=frag_kind,
            parent_id=parent_id,
        )
        return node_id

    def add_edge(self, src: str, dst: str, kind: CfgEdgeKind, label: str = "") -> None:
        """Append a directed edge."""
        self.graph.edges.append(CfgEdge(src=src, dst=dst, kind=kind, label=label))

    def link_many(self, srcs: list[str], dst: str, kind: CfgEdgeKind) -> None:
        """Connect each source in ``srcs`` to ``dst``."""
        for src in srcs:
            self.add_edge(src, dst, kind)

    def build_from_control_flow(self, cf: Any) -> CfgGraph:
        """Populate the graph from a ControlFlow-compatible root."""
        errors = tuple(tuple(e) for e in (getattr(cf, "errors", None) or ()))
        self.graph.errors = errors  # type: ignore[assignment]

        module_id = self.add_node(CfgNodeKind.MODULE, cf, label="<module>", prefix="module")
        entry_id = self.add_node(
            CfgNodeKind.ENTRY,
            label="<entry>",
            parent_id=module_id,
            span=_span_of(cf),
            prefix="entry",
        )
        exit_id = self.add_node(
            CfgNodeKind.EXIT,
            label="<exit>",
            parent_id=module_id,
            span=_span_of(cf),
            prefix="exit",
        )
        self.graph.entry_id = entry_id
        self.graph.exit_id = exit_id

        suite = list(getattr(cf, "suite", None) or [])
        first, falls = self._suite(suite, parent_id=module_id)
        if first is None:
            self.add_edge(entry_id, exit_id, CfgEdgeKind.NEXT)
        else:
            self.add_edge(entry_id, first, CfgEdgeKind.NEXT)
            self.link_many(falls, exit_id, CfgEdgeKind.EXIT)
        return self.graph

    def _suite(self, suite: list[Any], *, parent_id: str) -> tuple[Optional[str], list[str]]:
        """Wire a linear suite; return (first_id, fallthrough_exits)."""
        if not suite:
            return None, []
        first: Optional[str] = None
        prev_exits: list[str] = []
        for item in suite:
            item_entry, item_exits = self._item(item, parent_id=parent_id)
            if first is None:
                first = item_entry
            else:
                self.link_many(prev_exits, item_entry, CfgEdgeKind.NEXT)
            prev_exits = item_exits
        return first, prev_exits

    def _item(self, item: Any, *, parent_id: str) -> tuple[str, list[str]]:
        """Emit node(s) for one fragment; return (entry_id, fallthrough exits)."""
        frag_kind = int(getattr(item, "kind", -1))
        node_kind = _FRAG_TO_KIND.get(frag_kind, CfgNodeKind.CODE)

        if frag_kind == _IF:
            return self._if(item, parent_id=parent_id)
        if frag_kind in (_WHILE, _FOR):
            return self._loop(item, parent_id=parent_id)
        if frag_kind in (_TRY, _TRY_STAR):
            return self._try(item, parent_id=parent_id)
        if frag_kind == _MATCH:
            return self._match(item, parent_id=parent_id)
        if frag_kind == _WITH:
            return self._with(item, parent_id=parent_id)
        if frag_kind in (_FUNCTION, _CLASS):
            return self._scope(item, node_kind, parent_id=parent_id)

        node_id = self.add_node(node_kind, item, parent_id=parent_id)
        if node_kind in _TERMINAL_KINDS:
            self.add_edge(node_id, self.graph.exit_id, CfgEdgeKind.EXIT)
            return node_id, []
        return node_id, [node_id]

    def _scope(self, item: Any, kind: CfgNodeKind, *, parent_id: str) -> tuple[str, list[str]]:
        """Function/class: node + BODY into nested suite, then fallthrough."""
        node_id = self.add_node(kind, item, parent_id=parent_id)
        suite = list(getattr(item, "suite", None) or [])
        first, falls = self._suite(suite, parent_id=node_id)
        if first is not None:
            self.add_edge(node_id, first, CfgEdgeKind.BODY)
            # Nested terminals already wired to global EXIT; remaining falls stay internal.
            _ = falls
        return node_id, [node_id]

    def _with(self, item: Any, *, parent_id: str) -> tuple[str, list[str]]:
        """With statement: BODY into suite, then join."""
        node_id = self.add_node(CfgNodeKind.WITH, item, parent_id=parent_id)
        join_id = self.add_node(
            CfgNodeKind.JOIN,
            label="with_join",
            parent_id=node_id,
            span=_span_of(item),
            prefix="join",
        )
        suite = list(getattr(item, "suite", None) or [])
        first, falls = self._suite(suite, parent_id=node_id)
        if first is None:
            self.add_edge(node_id, join_id, CfgEdgeKind.BODY)
        else:
            self.add_edge(node_id, first, CfgEdgeKind.BODY)
            self.link_many(falls or [first], join_id, CfgEdgeKind.NEXT)
        return node_id, [join_id]

    def _if(self, item: Any, *, parent_id: str) -> tuple[str, list[str]]:
        """If/elif/else chain with a join node."""
        if_id = self.add_node(CfgNodeKind.IF, item, parent_id=parent_id)
        join_id = self.add_node(
            CfgNodeKind.JOIN,
            label="if_join",
            parent_id=if_id,
            span=_span_of(item),
            prefix="join",
        )
        parts = list(getattr(item, "parts", None) or [])
        prev: Optional[str] = if_id
        for idx, part in enumerate(parts):
            branch_id = self.add_node(CfgNodeKind.BRANCH, part, parent_id=if_id)
            if idx == 0:
                self.add_edge(if_id, branch_id, CfgEdgeKind.TRUE)
            elif prev is not None:
                self.add_edge(prev, branch_id, CfgEdgeKind.FALSE)
            suite = list(getattr(part, "suite", None) or [])
            first, falls = self._suite(suite, parent_id=branch_id)
            if first is None:
                self.add_edge(branch_id, join_id, CfgEdgeKind.BODY)
            else:
                self.add_edge(branch_id, first, CfgEdgeKind.BODY)
                self.link_many(falls or [first], join_id, CfgEdgeKind.NEXT)
            is_else = getattr(part, "condition", "x") is None
            prev = None if is_else else branch_id
        if prev is not None:
            self.add_edge(prev, join_id, CfgEdgeKind.FALSE)
        return if_id, [join_id]

    def _loop(self, item: Any, *, parent_id: str) -> tuple[str, list[str]]:
        """For/while with BODY, LOOP_BACK, optional ELSE, and join."""
        loop_id = self.add_node(CfgNodeKind.LOOP, item, parent_id=parent_id)
        join_id = self.add_node(
            CfgNodeKind.JOIN,
            label="loop_join",
            parent_id=loop_id,
            span=_span_of(item),
            prefix="join",
        )
        suite = list(getattr(item, "suite", None) or [])
        first, falls = self._suite(suite, parent_id=loop_id)
        if first is None:
            self.add_edge(loop_id, join_id, CfgEdgeKind.FALSE)
        else:
            self.add_edge(loop_id, first, CfgEdgeKind.BODY)
            self.link_many(falls or [first], loop_id, CfgEdgeKind.LOOP_BACK)
            self.add_edge(loop_id, join_id, CfgEdgeKind.FALSE)
        else_part = getattr(item, "elsePart", None)
        if else_part is not None:
            else_id = self.add_node(CfgNodeKind.BRANCH, else_part, parent_id=loop_id, label="else")
            self.add_edge(loop_id, else_id, CfgEdgeKind.ELSE)
            e_first, e_falls = self._suite(list(getattr(else_part, "suite", None) or []), parent_id=else_id)
            if e_first is None:
                self.add_edge(else_id, join_id, CfgEdgeKind.BODY)
            else:
                self.add_edge(else_id, e_first, CfgEdgeKind.BODY)
                self.link_many(e_falls or [e_first], join_id, CfgEdgeKind.NEXT)
        return loop_id, [join_id]

    def _try(self, item: Any, *, parent_id: str) -> tuple[str, list[str]]:
        """Try/except/else/finally with a join."""
        try_id = self.add_node(CfgNodeKind.TRY, item, parent_id=parent_id)
        join_id = self.add_node(
            CfgNodeKind.JOIN,
            label="try_join",
            parent_id=try_id,
            span=_span_of(item),
            prefix="join",
        )
        body_first, body_falls = self._suite(list(getattr(item, "suite", None) or []), parent_id=try_id)
        if body_first is None:
            self.add_edge(try_id, join_id, CfgEdgeKind.BODY)
            body_exits = [try_id]
        else:
            self.add_edge(try_id, body_first, CfgEdgeKind.BODY)
            body_exits = body_falls or [body_first]

        handler_exits: list[str] = []
        for part in list(getattr(item, "exceptParts", None) or []):
            branch_id = self.add_node(CfgNodeKind.BRANCH, part, parent_id=try_id)
            self.add_edge(try_id, branch_id, CfgEdgeKind.EXCEPT)
            first, falls = self._suite(list(getattr(part, "suite", None) or []), parent_id=branch_id)
            if first is None:
                self.add_edge(branch_id, join_id, CfgEdgeKind.BODY)
            else:
                self.add_edge(branch_id, first, CfgEdgeKind.BODY)
                handler_exits.extend(falls or [first])

        else_part = getattr(item, "elsePart", None)
        if else_part is not None:
            else_id = self.add_node(CfgNodeKind.BRANCH, else_part, parent_id=try_id, label="else")
            self.link_many(body_exits, else_id, CfgEdgeKind.ELSE)
            first, falls = self._suite(list(getattr(else_part, "suite", None) or []), parent_id=else_id)
            if first is None:
                self.add_edge(else_id, join_id, CfgEdgeKind.BODY)
            else:
                self.add_edge(else_id, first, CfgEdgeKind.BODY)
                handler_exits.extend(falls or [first])
        else:
            handler_exits.extend(body_exits)

        finally_part = getattr(item, "finallyPart", None)
        if finally_part is not None:
            fin_id = self.add_node(CfgNodeKind.BRANCH, finally_part, parent_id=try_id, label="finally")
            self.link_many(handler_exits or [try_id], fin_id, CfgEdgeKind.FINALLY)
            first, falls = self._suite(list(getattr(finally_part, "suite", None) or []), parent_id=fin_id)
            if first is None:
                self.add_edge(fin_id, join_id, CfgEdgeKind.BODY)
            else:
                self.add_edge(fin_id, first, CfgEdgeKind.BODY)
                self.link_many(falls or [first], join_id, CfgEdgeKind.NEXT)
        else:
            self.link_many(handler_exits or [try_id], join_id, CfgEdgeKind.NEXT)
        return try_id, [join_id]

    def _match(self, item: Any, *, parent_id: str) -> tuple[str, list[str]]:
        """Match/case with a join."""
        match_id = self.add_node(CfgNodeKind.MATCH, item, parent_id=parent_id)
        join_id = self.add_node(
            CfgNodeKind.JOIN,
            label="match_join",
            parent_id=match_id,
            span=_span_of(item),
            prefix="join",
        )
        parts = list(getattr(item, "parts", None) or [])
        if not parts:
            self.add_edge(match_id, join_id, CfgEdgeKind.NEXT)
            return match_id, [join_id]
        for part in parts:
            case_id = self.add_node(CfgNodeKind.BRANCH, part, parent_id=match_id)
            self.add_edge(match_id, case_id, CfgEdgeKind.CASE)
            first, falls = self._suite(list(getattr(part, "suite", None) or []), parent_id=case_id)
            if first is None:
                self.add_edge(case_id, join_id, CfgEdgeKind.BODY)
            else:
                self.add_edge(case_id, first, CfgEdgeKind.BODY)
                self.link_many(falls or [first], join_id, CfgEdgeKind.NEXT)
        return match_id, [join_id]


def _span_of(frag: Any) -> SourceSpan:
    """Extract a half-open SourceSpan from a fragment."""
    if frag is None:
        return SourceSpan(0, 0)
    if hasattr(frag, "getAbsPosRange"):
        begin, end = frag.getAbsPosRange()
        return SourceSpan(int(begin), int(end))
    body = getattr(frag, "body", None)
    if body is not None:
        return SourceSpan(int(getattr(body, "begin", 0)), int(getattr(body, "end", 0)))
    return SourceSpan(0, 0)


def from_control_flow(cf: Any) -> CfgGraph:
    """Build a :class:`CfgGraph` from a ControlFlow-compatible object."""
    return _Builder().build_from_control_flow(cf)


def build_cfg_graph(source: str) -> CfgGraph:
    """Parse ``source`` via ``core.flow`` and build a CFG graph."""
    from core.flow import parse_control_flow_from_memory

    return from_control_flow(parse_control_flow_from_memory(source))


def build_cfg_graph_from_file(path: str) -> CfgGraph:
    """Parse a file via ``core.flow`` and build a CFG graph."""
    from core.flow import parse_control_flow_from_file

    return from_control_flow(parse_control_flow_from_file(path))


__all__ = [
    "CfgEdge",
    "CfgEdgeKind",
    "CfgGraph",
    "CfgNode",
    "CfgNodeKind",
    "build_cfg_graph",
    "build_cfg_graph_from_file",
    "from_control_flow",
]
