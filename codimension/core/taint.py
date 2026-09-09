# -*- coding: utf-8 -*-
#
# codimension - function-local taint / data-flow MVP (R143 / R227 / R239 / R258 / R267)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Function-local taint / data-flow MVP (R143 / R227 / R239 / R258 / R267).

**Documented subset** (intentionally narrow):

* Scope: one ``FunctionDef`` / ``AsyncFunctionDef`` (by name, or the first
  in the module). Nested functions are analyzed separately when named;
  closures are not modeled.
* Sources: every formal parameter (including ``posonlyargs`` — R227); calls
  matching ``DEFAULT_SOURCE_CALLS`` (e.g. ``input``).
* Sinks: calls matching ``DEFAULT_SINK_CALLS`` (e.g. ``eval``, ``exec``,
  ``os.system``, ``subprocess.run`` / ``call`` / ``Popen``).
* Propagation (intra-procedural, name-based):
  assignment targets from tainted expressions; ``for`` loop targets from
  tainted iterables; unary/binary/bool/compare/if-exp; containers;
  attribute/subscript of a tainted value; call returns are tainted if
  any argument is tainted (unknown callees).
* Branches (R227 / R258 / R267): ``if`` / ``try`` / ``match`` clone the taint
  environment per arm and produce an ``ExitKind → env`` map. Fall-through
  uses the ``NORMAL`` entry only; terminal kinds bubble to enclosing
  statement lists (so nested loop ``break``/``continue`` are not lost).
* ``try``/``finally`` (R267): ``finally`` is analyzed **per exit edge**
  reaching it; a normal ``finally`` preserves the original exit kind with
  the post-``finally`` environment.
* Forward CFG (R239): statement lists are analyzed **once** in source order
  (no whole-list re-exec). Loop bodies use a local monotone worklist
  fixpoint on the back-edge only (``continue`` + normal end). ``try``
  handlers join environments from pre-try and post-statement throw points;
  non-exhaustive ``match`` joins the no-match fallthrough; loop ``else``
  uses the normal-termination lattice after the body (joined with the
  zero-iteration entry); ``break`` skips ``else``.
* Not modeled: interprocedural flow, field-sensitive keys, full exception
  CFG precision, comprehensions as full CFG, ``*args``/``**kwargs``
  unpacking fidelity, import aliases beyond a simple dotted callee string.

Pure stdlib ``ast``; no Qt. Absence of findings is **not** a security proof.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Optional, Sequence, cast

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

# Max back-edge iterations for may-taint loop fixpoint (R239).
_LOOP_FIXPOINT_FUEL = 8

Env = dict[str, tuple[str, int]]
ExitMap = dict["ExitKind", Env]


class ExitKind(str, Enum):
    """How a statement list leaves (R258 / R267 terminal-edge lattice)."""

    NORMAL = "normal"
    RETURN = "return"
    BREAK = "break"
    CONTINUE = "continue"
    RAISE = "raise"


@dataclass(frozen=True, slots=True)
class BranchResult:
    """Environment at the end of a branch plus its exit edge kind (R258).

    Prefer :class:`ExitMap` for multi-exit compounds (R267); this type remains
    for single-edge call sites and tests.
    """

    env: Env
    exit: ExitKind


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
    """Taint analysis result for one function.

    R194 / A222: the MVP is explicitly heuristic — absence of findings must
    not be read as a security proof. ``confidence`` is a fixed low value for
    the documented subset (not a measured coverage metric).
    """

    function: str
    begin_line: int
    end_line: int
    findings: tuple[TaintFinding, ...]
    parameters: tuple[str, ...]
    tainted_names: frozenset[str]
    heuristic: bool = True
    confidence: float = 0.4

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


def _formal_parameters(func: ast.AsyncFunctionDef | ast.FunctionDef) -> tuple[str, ...]:
    """Return all formal parameter names, including positional-only (R227)."""
    args = func.args
    names: list[str] = [arg.arg for arg in list(args.posonlyargs or []) + list(args.args or [])]
    if args.vararg is not None:
        names.append(args.vararg.arg)
    names.extend(arg.arg for arg in list(args.kwonlyargs or []))
    if args.kwarg is not None:
        names.append(args.kwarg.arg)
    return tuple(names)


def _join_may_taint(*envs: Env) -> Env:
    """May-taint lattice join: union of names; keep an origin from any arm (R227)."""
    out: Env = {}
    for env in envs:
        for name, origin in env.items():
            if name not in out:
                out[name] = origin
    return out


def _single_exit(kind: ExitKind, env: Env) -> ExitMap:
    """Build a one-edge exit map."""
    return {kind: dict(env)}


def _add_exit(dest: ExitMap, kind: ExitKind, env: Env) -> None:
    """May-join ``env`` into ``dest[kind]`` (R267)."""
    if kind in dest:
        dest[kind] = _join_may_taint(dest[kind], env)
    else:
        dest[kind] = dict(env)


def _merge_exits(*maps: ExitMap) -> ExitMap:
    """May-join exit maps by kind (R267)."""
    out: ExitMap = {}
    for mapping in maps:
        for kind, env in mapping.items():
            _add_exit(out, kind, env)
    return out


def _pattern_irrefutable(pattern: ast.pattern) -> bool:
    """True when ``pattern`` always matches (irrefutable capture / wildcard)."""
    if isinstance(pattern, ast.MatchAs) and pattern.pattern is None:
        return True
    if isinstance(pattern, ast.MatchOr):
        return any(_pattern_irrefutable(part) for part in pattern.patterns)
    return False


def _match_is_exhaustive(stmt: ast.Match) -> bool:
    """True when some unguarded case is irrefutable (no no-match fallthrough)."""
    for case in stmt.cases:
        if case.guard is not None:
            continue
        if _pattern_irrefutable(case.pattern):
            return True
    return False


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
        self.parameters = _formal_parameters(func)
        # name → source label that first tainted it
        self.origin: Env = {p: (f"param:{p}", _lineno(func)) for p in self.parameters}
        self.findings: list[TaintFinding] = []

    def tainted(self) -> set[str]:
        """Current set of tainted local names."""
        return set(self.origin)

    def mark(self, name: str, source: str, source_line: int) -> None:
        """Mark ``name`` tainted if not already."""
        if name not in self.origin:
            self.origin[name] = (source, source_line)

    def _analyze_branch(self, stmts: Iterable[ast.stmt], base: Env) -> ExitMap:
        """Run ``stmts`` on a clone of ``base``; return ExitKind→env map (R267)."""
        saved = self.origin
        self.origin = dict(base)
        try:
            return self.analyze_stmts(stmts)
        finally:
            self.origin = saved

    def _fixpoint_loop_body(
        self,
        body: Sequence[ast.stmt],
        entry: Env,
        *,
        fuel: int = _LOOP_FIXPOINT_FUEL,
    ) -> tuple[Env, list[Env], Env]:
        """Forward may-taint fixpoint for a loop body with a back-edge to the head.

        Back-edge uses NORMAL and CONTINUE exits only. Returns
        ``(normal_body_out, break_envs, head)`` at the fixpoint (R239 / R258 / R267).
        ``head`` is the iteration-boundary lattice (entry ∪ back-edges) used for
        loop-``else`` / zero-iteration joins; ``break`` does not feed it.

        Exit maps from the body bubble ``BREAK``/``CONTINUE`` directly — nested
        loops no longer share a mutable collector flag (R267).
        """
        head = dict(entry)
        body_out = dict(entry)
        break_envs: list[Env] = []
        for _ in range(max(1, fuel)):
            result = self._analyze_branch(body, head)
            if ExitKind.BREAK in result:
                break_envs.append(dict(result[ExitKind.BREAK]))

            back_envs: list[Env] = []
            if ExitKind.CONTINUE in result:
                back_envs.append(dict(result[ExitKind.CONTINUE]))
            if ExitKind.NORMAL in result:
                body_out = dict(result[ExitKind.NORMAL])
                back_envs.append(body_out)

            new_head = _join_may_taint(entry, *back_envs) if back_envs else dict(entry)
            if new_head == head:
                return body_out, break_envs, head
            head = new_head

        result = self._analyze_branch(body, head)
        if ExitKind.BREAK in result:
            break_envs.append(dict(result[ExitKind.BREAK]))
        if ExitKind.NORMAL in result:
            body_out = dict(result[ExitKind.NORMAL])
        if ExitKind.CONTINUE in result:
            head = _join_may_taint(entry, result[ExitKind.CONTINUE])
        return body_out, break_envs, head

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

    def analyze_stmts(self, stmts: Iterable[ast.stmt]) -> ExitMap:
        """Forward-analyze a statement list; bubble terminal ExitKind→env (R267).

        ``NORMAL`` continues to the next statement; other kinds accumulate and
        escape the list when there is no fall-through left.
        """
        terminals: ExitMap = {}
        for stmt in stmts:
            exits = self.analyze_stmt(stmt)
            for kind, env in exits.items():
                if kind is not ExitKind.NORMAL:
                    _add_exit(terminals, kind, env)
            if ExitKind.NORMAL not in exits:
                return terminals
            self.origin = exits[ExitKind.NORMAL]
        _add_exit(terminals, ExitKind.NORMAL, self.origin)
        return terminals

    def analyze_stmt(self, stmt: ast.stmt) -> ExitMap:
        """Dispatch one statement (transfer function) → ExitKind→env (R267)."""
        if isinstance(stmt, ast.Assign):
            self.apply_assign(stmt.targets, stmt.value)
            return _single_exit(ExitKind.NORMAL, self.origin)
        if isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
            self.apply_assign([stmt.target], stmt.value)
            return _single_exit(ExitKind.NORMAL, self.origin)
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
            return _single_exit(ExitKind.NORMAL, self.origin)
        if isinstance(stmt, ast.Expr):
            self.visit_expr_calls(stmt.value)
            return _single_exit(ExitKind.NORMAL, self.origin)
        if isinstance(stmt, ast.Return):
            if stmt.value is not None:
                self.visit_expr_calls(stmt.value)
            return _single_exit(ExitKind.RETURN, self.origin)
        if isinstance(stmt, ast.Break):
            return _single_exit(ExitKind.BREAK, self.origin)
        if isinstance(stmt, ast.Continue):
            return _single_exit(ExitKind.CONTINUE, self.origin)
        if isinstance(stmt, ast.Raise):
            if stmt.exc is not None:
                self.visit_expr_calls(stmt.exc)
            if stmt.cause is not None:
                self.visit_expr_calls(stmt.cause)
            return _single_exit(ExitKind.RAISE, self.origin)
        if isinstance(stmt, ast.If):
            return self._analyze_if(stmt)
        if isinstance(stmt, (ast.For, ast.AsyncFor)):
            self._analyze_for_loop(stmt)
            return _single_exit(ExitKind.NORMAL, self.origin)
        if isinstance(stmt, ast.While):
            self._analyze_while_loop(stmt)
            return _single_exit(ExitKind.NORMAL, self.origin)
        if isinstance(stmt, (ast.With, ast.AsyncWith)):
            for item in stmt.items:
                self.visit_expr_calls(item.context_expr)
                if item.optional_vars is not None:
                    hit = self.expr_tainted(item.context_expr)
                    if hit:
                        for name in _assign_targets(item.optional_vars):
                            self.mark(name, hit[0], hit[1])
            return self.analyze_stmts(stmt.body)
        if isinstance(stmt, ast.Try):
            return self._analyze_try(stmt)
        if isinstance(stmt, ast.Match):  # py3.10+
            return self._analyze_match(stmt)
        # Nested def/class: ignore body (separate analysis unit).
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return _single_exit(ExitKind.NORMAL, self.origin)
        # Fallback: still scan for sink calls inside the statement.
        for child in ast.walk(stmt):
            if isinstance(child, ast.Call):
                self.check_sink(child)
        return _single_exit(ExitKind.NORMAL, self.origin)

    def _analyze_if(self, stmt: ast.If) -> ExitMap:
        """If/else: merge full ExitKind→env maps from both arms (R258 / R267)."""
        self.visit_expr_calls(stmt.test)
        base = dict(self.origin)
        body = self._analyze_branch(stmt.body, base)
        else_arm = self._analyze_branch(stmt.orelse, base) if stmt.orelse else _single_exit(ExitKind.NORMAL, base)
        return _merge_exits(body, else_arm)

    def _analyze_for_loop(self, stmt: ast.For | ast.AsyncFor) -> None:
        """For/AsyncFor: bind targets, fixpoint body; else skips break (R258)."""
        self.visit_expr_calls(stmt.iter)
        hit = self.expr_tainted(stmt.iter)
        if hit:
            for name in _assign_targets(stmt.target):
                self.mark(name, hit[0], hit[1])
        entry = dict(self.origin)
        body_out, break_envs, head = self._fixpoint_loop_body(stmt.body, entry)
        # else / zero-iter: iteration-boundary head (NORMAL+CONTINUE back-edges),
        # not break exits (R258).
        else_in = head
        if stmt.orelse:
            else_result = self._analyze_branch(stmt.orelse, else_in)
            else_env = else_result.get(ExitKind.NORMAL, else_in)
        else:
            else_env = else_in
        # After the loop: normal completion (via else) ∪ break exits.
        after_envs: list[Env] = [else_env, *break_envs]
        if not stmt.orelse:
            after_envs.append(body_out)
        self.origin = _join_may_taint(*after_envs)

    def _analyze_while_loop(self, stmt: ast.While) -> None:
        """While: fixpoint body; else uses iteration-boundary head (R239 / R258)."""
        self.visit_expr_calls(stmt.test)
        entry = dict(self.origin)
        body_out, break_envs, head = self._fixpoint_loop_body(stmt.body, entry)
        else_in = head
        if stmt.orelse:
            else_result = self._analyze_branch(stmt.orelse, else_in)
            else_env = else_result.get(ExitKind.NORMAL, else_in)
        else:
            else_env = else_in
        after_envs: list[Env] = [else_env, *break_envs]
        if not stmt.orelse:
            after_envs.append(body_out)
        self.origin = _join_may_taint(*after_envs)

    def _analyze_try(self, stmt: ast.Try) -> ExitMap:
        """Try/except/else/finally with per-edge finally transfer (R239 / R267)."""
        base = dict(self.origin)
        throw_envs: list[Env] = [dict(base)]
        saved = self.origin
        self.origin = dict(base)
        body_exits: ExitMap = {}
        try:
            for body_stmt in stmt.body:
                exits = self.analyze_stmt(body_stmt)
                for kind, env in exits.items():
                    if kind is not ExitKind.NORMAL:
                        _add_exit(body_exits, kind, env)
                if ExitKind.NORMAL not in exits:
                    break
                self.origin = exits[ExitKind.NORMAL]
                throw_envs.append(dict(self.origin))
            else:
                _add_exit(body_exits, ExitKind.NORMAL, self.origin)
        finally:
            self.origin = saved

        handler_in = _join_may_taint(*throw_envs)
        handler_maps = [self._analyze_branch(handler.body, handler_in) for handler in stmt.handlers]
        handlers_merged = _merge_exits(*handler_maps) if handler_maps else {}

        # orelse runs only on NORMAL completion of the try body.
        if stmt.orelse and ExitKind.NORMAL in body_exits:
            else_map = self._analyze_branch(stmt.orelse, body_exits[ExitKind.NORMAL])
        elif ExitKind.NORMAL in body_exits:
            else_map = _single_exit(ExitKind.NORMAL, body_exits[ExitKind.NORMAL])
        else:
            else_map = {}

        body_terminals: ExitMap = {}
        for kind, env in body_exits.items():
            if kind is not ExitKind.NORMAL:
                body_terminals[kind] = env
        before_finally = _merge_exits(cast(ExitMap, body_terminals), handlers_merged, else_map)

        if not stmt.finalbody:
            if ExitKind.NORMAL in before_finally:
                self.origin = before_finally[ExitKind.NORMAL]
            return before_finally

        after_finally: ExitMap = {}
        for kind, env in before_finally.items():
            fin = self._analyze_branch(stmt.finalbody, env)
            if ExitKind.NORMAL in fin:
                # Normal finally completion preserves the incoming exit kind.
                _add_exit(after_finally, kind, fin[ExitKind.NORMAL])
            for fin_kind, fin_env in fin.items():
                if fin_kind is ExitKind.NORMAL:
                    continue
                # finally diverted the edge (return / raise / break / continue).
                _add_exit(after_finally, fin_kind, fin_env)

        if ExitKind.NORMAL in after_finally:
            self.origin = after_finally[ExitKind.NORMAL]
        return after_finally

    def _analyze_match(self, stmt: ast.Match) -> ExitMap:
        """Match/case: merge ExitKind→env maps; non-exhaustive fallthrough."""
        self.visit_expr_calls(stmt.subject)
        base = dict(self.origin)
        case_maps = [self._analyze_branch(case.body, base) for case in stmt.cases]
        arms: list[ExitMap] = list(case_maps)
        if not _match_is_exhaustive(stmt):
            arms.append(_single_exit(ExitKind.NORMAL, base))
        if not arms:
            return _single_exit(ExitKind.NORMAL, base)
        return _merge_exits(*arms)

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
    "BranchResult",
    "ExitKind",
    "TaintFinding",
    "TaintReport",
    "analyze_function_taint",
    "analyze_function_taint_from_file",
]
