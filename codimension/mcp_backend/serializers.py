# -*- coding: utf-8 -*-
#
# codimension - MCP JSON serializers (R182)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""JSON-friendly serializers for MCP tool results (R182)."""

from __future__ import annotations

from typing import Any

from core.cfg import CfgGraph, CfgNode
from core.symbol_index import SymbolRecord
from core.taint import TaintFinding, TaintReport


def symbol_to_dict(record: SymbolRecord) -> dict[str, Any]:
    """Serialize one :class:`SymbolRecord`."""
    return {
        "name": record.name,
        "kind": record.kind.value,
        "file": record.file,
        "qualname": record.qualname,
        "container": record.container,
        "line": record.line,
        "span": {"start": record.span.start, "end": record.span.end},
    }


def cfg_node_to_dict(node: CfgNode) -> dict[str, Any]:
    """Serialize one CFG node."""
    return {
        "id": node.id,
        "kind": node.kind.value,
        "label": node.label,
        "begin_line": node.begin_line,
        "end_line": node.end_line,
        "parent_id": node.parent_id,
        "span": {"start": node.span.start, "end": node.span.end},
    }


def cfg_graph_to_dict(graph: CfgGraph) -> dict[str, Any]:
    """Serialize a :class:`CfgGraph` for MCP clients."""
    return {
        "entry_id": graph.entry_id,
        "exit_id": graph.exit_id,
        "nodes": [cfg_node_to_dict(n) for n in graph.nodes.values()],
        "edges": [{"src": e.src, "dst": e.dst, "kind": e.kind.value, "label": e.label} for e in graph.edges],
        "errors": [{"line": ln, "col": col, "message": msg} for ln, col, msg in graph.errors],
    }


def taint_finding_to_dict(finding: TaintFinding) -> dict[str, Any]:
    """Serialize one taint finding."""
    return {
        "function": finding.function,
        "sink": finding.sink,
        "sink_line": finding.sink_line,
        "source": finding.source,
        "source_line": finding.source_line,
        "via_names": list(finding.via_names),
    }


def taint_report_to_dict(report: TaintReport) -> dict[str, Any]:
    """Serialize a :class:`TaintReport` (includes heuristic disclaimer fields)."""
    return {
        "function": report.function,
        "begin_line": report.begin_line,
        "end_line": report.end_line,
        "findings": [taint_finding_to_dict(f) for f in report.findings],
        "parameters": list(report.parameters),
        "tainted_names": sorted(report.tainted_names),
        "heuristic": report.heuristic,
        "confidence": report.confidence,
        "empty": report.empty,
    }


__all__ = [
    "cfg_graph_to_dict",
    "cfg_node_to_dict",
    "symbol_to_dict",
    "taint_finding_to_dict",
    "taint_report_to_dict",
]
