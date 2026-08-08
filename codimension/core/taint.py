# -*- coding: utf-8 -*-
#
# codimension - function-local taint / data-flow MVP (R143)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Function-local taint / data-flow MVP (R143).

**Documented subset** (intentionally narrow):

* Scope: one ``FunctionDef`` / ``AsyncFunctionDef`` (by name, or the first
  in the module). Nested functions are analyzed separately when named;
  closures are not modeled.
* Sources: every formal parameter; calls matching
  ``DEFAULT_SOURCE_CALLS`` (e.g. ``input``).
* Sinks: calls matching ``DEFAULT_SINK_CALLS`` (e.g. ``eval``, ``exec``,
  ``os.system``, ``subprocess.run`` / ``call`` / ``Popen``).
* Propagation (intra-procedural, name-based, path-insensitive union):
  assignment targets from tainted expressions; ``for`` loop targets from
  tainted iterables; unary/binary/bool/compare/if-exp; containers;
  attribute/subscript of a tainted value; call returns are tainted if
  any argument is tainted (unknown callees).
* Not modeled: interprocedural flow, field-sensitive keys, exceptions,
  comprehensions as full CFG, ``*args``/``**kwargs`` unpacking fidelity,
  import aliases beyond a simple dotted callee string.

Pure stdlib ``ast``; no Qt.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

# Qualname suffixes / exact names treated as sources when called.
DEFAULT_SOURCE_CALLS: frozenset[str] = frozenset(
    {
        "input",
        "builtins.input",
        "sys.stdin.readline",
        "sys.stdin.read",
    }
)

# Qualname suffixes / exact names treated as sinks when called.
DEFAULT_SINK_CALLS: frozenset[str] = frozenset(
    {
        "eval",
        "exec",
        "builtins.eval",
        "builtins.exec",
        "os.system",
        "os.popen",
        "subprocess.call",
        "subprocess.run",
        "subprocess.Popen",
        "subprocess.check_output",
        "subprocess.check_call",
    }
)


@dataclass(frozen=True)
class TaintFinding:
    """One source → sink flow inside a single function."""

    function: str
    sink: str
    sink_line: int
    source: str
    source_line: int
    via_names: tuple[str, ...]


@dataclass(frozen=True)
class TaintReport:
    """Taint analysis result for one function."""

    function: str
    begin_line: int
    end_line: int
    findings: tuple[TaintFinding, ...]
    parameters: tuple[str, ...]
    tainted_names: frozenset[str]

    @property
    def empty(self) -> bool:
        """True when no source→sink findings were recorded."""
        return not self.findings


def _lineno(node: ast.AST) -> int:
    """Best-effort 1-based line for a node."""
    return int(getattr(node, "lineno", 1) or 1)


def _callee_name(node: ast.AST) -> str:
    """Dotted callee string for a Call's ``func``, or empty."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _callee_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _matches_catalog(name: str, catalog: frozenset[str]) -> bool:
    """True if ``name`` equals or ends with a catalog entry."""
    if not name:
        return False
    if name in catalog:
        return True
    return any(name.endswith("." + item) or name == item for item in catalog)


def _assign_targets(target: ast.AST) -> list[str]:
    """Collect simple name targets from an assignment target tree."""
    names: list[str] = []
    if isinstance(target, ast.Name):
        names.append(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            names.extend(_assign_targets(elt))
    elif isinstance(target, ast.Starred):
        names.extend(_assign_targets(target.value))
    return names


class _FunctionTaint:
    """Mutable analyzer state for one function body."""

    def __init__(
        self,
        func: ast.AsyncFunctionDef | ast.FunctionDef,
        *,
        sources: frozenset[str],
        sinks: frozenset[str],
    ) -> None:
        self.func = func
        self.sources = sources
        self.sinks = sinks
        self.func_name = func.name
        self.parameters = tuple(arg.arg for arg in func.args.args) + tuple(arg.arg for arg in func.args.kwonlyargs)
        if func.args.vararg is not None:
            self.parameters = self.parameters + (func.args.vararg.arg,)
        if func.args.kwarg is not None:
            self.parameters = self.parameters + (func.args.kwarg.arg,)
        # name → source label that first tainted it
        self.origin: dict[str, tuple[str, int]] = {p: (f"param:{p}", _lineno(func)) for p in self.parameters}
        self.findings: list[TaintFinding] = []

    def tainted(self) -> set[str]:
        """Current set of tainted local names."""
        return set(self.origin)

    def mark(self, name: str, source: str, source_line: int) -> None:
        """Mark ``name`` tainted if not already."""
        if name not in self.origin:
            self.origin[name] = (source, source_line)

    def expr_tainted(self, node: Optional[ast.AST]) -> Optional[tuple[str, int]]:
        """Return (source, source_line) if ``node`` may carry taint."""
        if node is None:
            return None
        if isinstance(node, ast.Name):
            return self.origin.get(node.id)
        if isinstance(node, ast.Constant):
            return None
        if isinstance(node, ast.Call):
            cname = _callee_name(node.func)
            if _matches_catalog(cname, self.sources):
                return (f"call:{cname}", _lineno(node))
            # Propagate through unknown calls if any arg/kw is tainted.
            for arg in node.args:
                hit = self.expr_tainted(arg)
                if hit:
                    return hit
            for kw in node.keywords:
                hit = self.expr_tainted(kw.value)
                if hit:
                    return hit
            return None
        if isinstance(node, ast.Attribute):
            return self.expr_tainted(node.value)
        if isinstance(node, ast.Subscript):
            return self.expr_tainted(node.value) or self.expr_tainted(node.slice)
        if isinstance(node, ast.UnaryOp):
            return self.expr_tainted(node.operand)
        if isinstance(node, ast.BinOp):
            return self.expr_tainted(node.left) or self.expr_tainted(node.right)
        if isinstance(node, ast.BoolOp):
            for value in node.values:
                hit = self.expr_tainted(value)
                if hit:
                    return hit
            return None
        if isinstance(node, ast.Compare):
            hit = self.expr_tainted(node.left)
            if hit:
                return hit
            for comp in node.comparators:
                hit = self.expr_tainted(comp)
                if hit:
                    return hit
            return None
        if isinstance(node, ast.IfExp):
            return self.expr_tainted(node.body) or self.expr_tainted(node.orelse) or self.expr_tainted(node.test)
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            for elt in node.elts:
                hit = self.expr_tainted(elt)
                if hit:
                    return hit
            return None
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                hit = self.expr_tainted(value) or self.expr_tainted(key)
                if hit:
                    return hit
            return None
        if isinstance(node, ast.JoinedStr):  # f-string
            for value in node.values:
                hit = self.expr_tainted(value)
                if hit:
                    return hit
            return None
        if isinstance(node, ast.FormattedValue):
            return self.expr_tainted(node.value)
        if isinstance(node, ast.Starred):
            return self.expr_tainted(node.value)
        return None

    def check_sink(self, call: ast.Call) -> None:
        """Record a finding if ``call`` is a sink with a tainted argument."""
        cname = _callee_name(call.func)
        if not _matches_catalog(cname, self.sinks):
            return
        hit: Optional[tuple[str, int]] = None
        via: list[str] = []
        for arg in list(call.args) + [kw.value for kw in call.keywords]:
            one = self.expr_tainted(arg)
            if one and hit is None:
                hit = one
            if isinstance(arg, ast.Name) and arg.id in self.origin:
                via.append(arg.id)
        if hit is None:
            return
        source, source_line = hit
        self.findings.append(
            TaintFinding(
                function=self.func_name,
                sink=cname,
                sink_line=_lineno(call),
                source=source,
                source_line=source_line,
                via_names=tuple(dict.fromkeys(via)),
            )
        )

    def visit_expr_calls(self, node: ast.AST) -> None:
        """Walk an expression tree for sink calls (side-effect check)."""
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                self.check_sink(child)

    def apply_assign(self, targets: Sequence[ast.AST], value: ast.AST) -> None:
        """Propagate taint from ``value`` into simple name ``targets``."""
        self.visit_expr_calls(value)
        hit = self.expr_tainted(value)
        names: list[str] = []
        for target in targets:
            names.extend(_assign_targets(target))
            self.visit_expr_calls(target)
        if hit is None:
            # Overwrite: assignment from clean value clears taint.
            for name in names:
                self.origin.pop(name, None)
            return
        source, source_line = hit
        for name in names:
            self.mark(name, source, source_line)

    def analyze_stmts(self, stmts: Iterable[ast.stmt], *, _fuel: int = 8) -> None:
        """Analyze a statement list; loops re-run until fixpoint or fuel out."""
        for _ in range(max(1, _fuel)):
            snapshot = frozenset(self.origin.items())
            for stmt in stmts:
                self.analyze_stmt(stmt)
            if frozenset(self.origin.items()) == snapshot:
                break

    def analyze_stmt(self, stmt: ast.stmt) -> None:
        """Dispatch one statement."""
        if isinstance(stmt, ast.Assign):
            self.apply_assign(stmt.targets, stmt.value)
            return
        if isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
            self.apply_assign([stmt.target], stmt.value)
            return
        if isinstance(stmt, ast.AugAssign):
            # x += y : tainted if x or y tainted
            self.visit_expr_calls(stmt.value)
            hit = self.expr_tainted(stmt.value) or (
                self.origin.get(stmt.target.id) if isinstance(stmt.target, ast.Name) else None
            )
            names = _assign_targets(stmt.target)
            if hit:
                for name in names:
                    self.mark(name, hit[0], hit[1])
            return
        if isinstance(stmt, ast.Expr):
            self.visit_expr_calls(stmt.value)
            return
        if isinstance(stmt, ast.Return):
            if stmt.value is not None:
                self.visit_expr_calls(stmt.value)
            return
        if isinstance(stmt, ast.If):
            self.visit_expr_calls(stmt.test)
            self.analyze_stmts(stmt.body)
            self.analyze_stmts(stmt.orelse)
            return
        if isinstance(stmt, (ast.For, ast.AsyncFor)):
            self.visit_expr_calls(stmt.iter)
            hit = self.expr_tainted(stmt.iter)
            if hit:
                for name in _assign_targets(stmt.target):
                    self.mark(name, hit[0], hit[1])
            self.analyze_stmts(stmt.body)
            self.analyze_stmts(stmt.orelse)
            return
        if isinstance(stmt, (ast.While,)):
            self.visit_expr_calls(stmt.test)
            self.analyze_stmts(stmt.body)
            self.analyze_stmts(stmt.orelse)
            return
        if isinstance(stmt, (ast.With, ast.AsyncWith)):
            for item in stmt.items:
                self.visit_expr_calls(item.context_expr)
                if item.optional_vars is not None:
                    hit = self.expr_tainted(item.context_expr)
                    if hit:
                        for name in _assign_targets(item.optional_vars):
                            self.mark(name, hit[0], hit[1])
            self.analyze_stmts(stmt.body)
            return
        if isinstance(stmt, ast.Try):
            self.analyze_stmts(stmt.body)
            for handler in stmt.handlers:
                self.analyze_stmts(handler.body)
            self.analyze_stmts(stmt.orelse)
            self.analyze_stmts(stmt.finalbody)
            return
        if isinstance(stmt, ast.Match):  # py3.10+
            self.visit_expr_calls(stmt.subject)
            for case in stmt.cases:
                self.analyze_stmts(case.body)
            return
        # Nested def/class: ignore body (separate analysis unit).
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return
        # Fallback: still scan for sink calls inside the statement.
        for child in ast.walk(stmt):
            if isinstance(child, ast.Call):
                self.check_sink(child)

    def run(self) -> TaintReport:
        """Analyze the function and return a report."""
        self.analyze_stmts(self.func.body)
        end = _lineno(self.func)
        for node in ast.walk(self.func):
            end = max(end, _lineno(node))
        # Deduplicate findings by sink line + source + sink name
        uniq: dict[tuple[str, int, str, int], TaintFinding] = {}
        for finding in self.findings:
            key = (finding.sink, finding.sink_line, finding.source, finding.source_line)
            uniq[key] = finding
        return TaintReport(
            function=self.func_name,
            begin_line=_lineno(self.func),
            end_line=end,
            findings=tuple(sorted(uniq.values(), key=lambda f: (f.sink_line, f.source, f.sink))),
            parameters=self.parameters,
            tainted_names=frozenset(self.origin),
        )


def _find_function(tree: ast.AST, name: Optional[str]) -> ast.AsyncFunctionDef | ast.FunctionDef:
    """Return the requested function node or raise ``ValueError``."""
    functions: list[ast.AsyncFunctionDef | ast.FunctionDef] = []
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node)
            if name is not None and node.name == name:
                return node
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions.append(child)
                    if name is not None and child.name == name:
                        return child
    if name is not None:
        raise ValueError(f"function {name!r} not found")
    if not functions:
        raise ValueError("no function definition found in source")
    return functions[0]


def analyze_function_taint(
    source: str,
    *,
    function: Optional[str] = None,
    source_calls: Optional[Iterable[str]] = None,
    sink_calls: Optional[Iterable[str]] = None,
) -> TaintReport:
    """Analyze one function in ``source`` for parameter/call → sink flows."""
    tree = ast.parse(source)
    func = _find_function(tree, function)
    sources = frozenset(source_calls) if source_calls is not None else DEFAULT_SOURCE_CALLS
    sinks = frozenset(sink_calls) if sink_calls is not None else DEFAULT_SINK_CALLS
    return _FunctionTaint(func, sources=sources, sinks=sinks).run()


def analyze_function_taint_from_file(
    path: str,
    *,
    function: Optional[str] = None,
    source_calls: Optional[Iterable[str]] = None,
    sink_calls: Optional[Iterable[str]] = None,
) -> TaintReport:
    """Read ``path`` and run :func:`analyze_function_taint`."""
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    return analyze_function_taint(
        source,
        function=function,
        source_calls=source_calls,
        sink_calls=sink_calls,
    )


__all__ = [
    "DEFAULT_SINK_CALLS",
    "DEFAULT_SOURCE_CALLS",
    "TaintFinding",
    "TaintReport",
    "analyze_function_taint",
    "analyze_function_taint_from_file",
]
