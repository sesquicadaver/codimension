# -*- coding: utf-8 -*-
#
# codimension - AI analysis / docstring task model (Qt-free)
# Copyright (C) 2026  Codimension Team
# The license is described in the LICENSE file at the root directory.
#

"""Scoped AI tasks: project/module/symbol analysis and Google docstrings.

Pure orchestration: callers supply a ``complete_fn(system, user) -> str``
(usually a live LLM backend). Offline heuristics are intentionally not used
for these tasks.

R231: ``ANALYZE_PROJECT`` emits validated :class:`~core.ai_findings.AiFinding`
records and enforces a global token/cost budget beyond per-file truncation.

R241: immutable :class:`~core.ai_budget.AiJobContract` (files/requests/source
bytes/output tokens/deadline), cancellation token, provider output caps,
post-response hard budget checks, and audit-level finding validation.

R249: provider ``max_output_tokens`` is the cost- and token-aware remainder
(not a fixed completion reserve that under-reserves relative to the actual cap).
"""

from __future__ import annotations

import inspect
import os
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterable, Mapping, Optional, Sequence

from core.ai_budget import (
    AiBudgetExceeded,
    AiBudgetLimits,
    AiBudgetTracker,
    AiJobContract,
    estimate_tokens,
    load_ai_budget_limits,
    load_ai_job_contract,
)
from core.ai_context import AiContextPack, build_ai_context_from_source
from core.ai_docstring import DocstringTarget, build_docstring_target
from core.ai_docstring_context import (
    build_docstring_support_context,
    resolve_docstring_fragment,
)
from core.ai_findings import (
    AiFinding,
    AiFindingsReport,
    dedupe_findings,
    parse_findings_payload,
    validate_audit_finding,
)
from core.ai_project_context import (
    assert_path_in_project,
    build_project_module_context,
)
from core.symbol_index import SymbolKind

CompleteFn = Callable[..., str]
ProgressFn = Callable[[str], None]
CancelCheck = Callable[[], bool]

MAX_MODULE_CHARS = 12000
MAX_CHUNK_REPORT_CHARS = 6000
DOCSTRING_STYLE = "Google"


class AiTaskCancelled(RuntimeError):
    """Raised when an AI job observes a cancellation request (R241)."""


class AiTaskDeadlineExceeded(RuntimeError):
    """Raised when an AI job exceeds its wall-clock deadline (R241)."""


class AiTaskKind(str, Enum):
    """User-facing AI operations (base set + chat)."""

    ANALYZE_PROJECT = "analyze_project"
    ANALYZE_MODULE = "analyze_module"
    ANALYZE_SYMBOL = "analyze_symbol"
    DOCSTRING = "docstring"
    CHAT = "chat"


@dataclass(frozen=True)
class AiTaskRequest:
    """One AI job with an explicit scope."""

    kind: AiTaskKind
    title: str
    file_path: str = ""
    source: str = ""
    symbol_name: str = ""
    symbol_kind: Optional[SymbolKind] = None
    project_files: tuple[str, ...] = ()
    project_dir: str = ""
    chat_message: str = ""
    chat_history: tuple[tuple[str, str], ...] = ()
    selected_text: str = ""
    cursor_line: int = 0


@dataclass(frozen=True)
class AiTaskResult:
    """Text result for the AI Result / Chat panel.

    R231: project analysis may also carry validated ``findings`` and budget
    accounting (tokens/cost estimates; ``budget_stopped`` when the global cap
    halted further LLM calls).
    """

    kind: AiTaskKind
    title: str
    text: str
    backend_name: str
    file_path: str = ""
    symbol_name: str = ""
    docstring_target: Optional[DocstringTarget] = None
    findings: tuple[AiFinding, ...] = ()
    findings_report: Optional[AiFindingsReport] = None
    budget_tokens_used: int = 0
    budget_cost_usd: float = 0.0
    budget_stopped: bool = False


def list_project_py_files(files_list: Iterable[str], project_dir: str) -> tuple[str, ...]:
    """Return absolute paths of ``.py`` files from a Codimension ``filesList``."""
    out: list[str] = []
    seen: set[str] = set()
    project_dir = os.path.abspath(project_dir or "")
    for item in files_list:
        if not item or str(item).endswith(os.path.sep):
            continue
        path = str(item)
        if not path.lower().endswith(".py"):
            continue
        full = path if os.path.isabs(path) else os.path.normpath(os.path.join(project_dir, path))
        full = os.path.abspath(full)
        if full in seen or not os.path.isfile(full):
            continue
        seen.add(full)
        out.append(full)
    out.sort()
    return tuple(out)


def _truncate(text: str, limit: int) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[: limit - 20] + "\n\n...[truncated]...\n"


def _read_text(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read()


def _system_analyst() -> str:
    return (
        "You are a senior Python engineer inside the Codimension IDE. "
        "Be concrete, structured, and actionable. Use markdown headings and bullets. "
        "Stay strictly inside the provided project context: do not invent project "
        "modules, symbols, or algorithms that are not evidenced in the sources. "
        "Do not invent APIs that are not in the provided source."
    )


def _system_docstring() -> str:
    return (
        "You write Google-style Python docstrings only. "
        "Return ONLY the docstring body suitable to place inside triple quotes "
        "(no surrounding quotes, no code fences, no prose outside the docstring). "
        "Include Args / Returns / Raises sections when applicable. "
        "The Selected fragment is authoritative: document that code. "
        "Use Supporting context only for names, imports, and enclosing signature — "
        "do not invent behavior absent from the fragment. "
        "Never claim that information is missing when a Selected fragment is provided."
    )


def build_module_analysis_prompt(
    path: str,
    source: str,
    *,
    project_context_block: str = "",
) -> tuple[str, str]:
    """System + user prompts for project-scoped module analysis."""
    ctx = (project_context_block or "").strip()
    user_parts = [
        "Analyze this Python module end-to-end **within the open Codimension project**.",
        f"File: {path}",
        "",
        "Cover: purpose in the project, public API, key types/functions, "
        "how it couples to other project modules, control-flow risks, "
        "and concrete improvement suggestions that preserve project algorithms.",
        "",
    ]
    if ctx:
        user_parts.append(ctx)
        user_parts.append("")
    user_parts.append("Module source:")
    user_parts.append(_truncate(source, MAX_MODULE_CHARS))
    return _system_analyst(), "\n".join(user_parts)


def build_symbol_analysis_prompt(pack: AiContextPack) -> tuple[str, str]:
    """System + user prompts for function/class analysis."""
    user = (
        f"Analyze this Python symbol in depth.\n"
        f"Symbol: {pack.symbol.qualname or pack.symbol.name} ({pack.symbol.kind.value})\n"
        f"File: {pack.symbol.file}:{pack.excerpt_begin_line}-{pack.excerpt_end_line}\n"
        f"Definitions: {len(pack.definitions)}; references: {len(pack.references)}\n\n"
        f"Cover: responsibility, inputs/outputs, edge cases, CFG complexity, "
        f"and concrete refactor notes.\n\n"
        f"Source excerpt:\n{_truncate(pack.source_excerpt, MAX_MODULE_CHARS)}"
    )
    return _system_analyst(), user


def build_docstring_prompt(
    *,
    symbol_name: str,
    file_path: str,
    selected_fragment: str,
    support_context: str = "",
) -> tuple[str, str]:
    """System + user prompts for a Google-style docstring.

    ``selected_fragment`` is the code to document. ``support_context`` is lean
    module/enclosing info so the model does not invent or refuse for lack of data.
    """
    fragment = (selected_fragment or "").strip()
    if not fragment:
        raise ValueError("docstring prompt requires a non-empty selected fragment")
    support = (support_context or "").strip() or "(none)"
    user = (
        f"Write a {DOCSTRING_STYLE}-style docstring for the selected Python code.\n"
        f"Symbol (apply target, if known): {symbol_name or '(unknown)'}\n"
        f"File: {file_path or '<buffer>'}\n\n"
        f"## Selected fragment (authoritative — write the docstring for THIS code)\n"
        f"{_truncate(fragment, MAX_MODULE_CHARS)}\n\n"
        f"## Supporting context (names/signature/imports only; do not invent beyond this)\n"
        f"{_truncate(support, MAX_MODULE_CHARS)}"
    )
    return _system_docstring(), user


def build_project_chunk_prompt(path: str, source: str, index: int, total: int) -> tuple[str, str]:
    """Per-file project analysis chunk requesting structured findings JSON."""
    user = (
        f"Project analysis chunk {index}/{total}.\n"
        f"File: {path}\n\n"
        "Return a JSON object with a `findings` array. Each finding must include:\n"
        "`title`, `message`, `severity` (error|warning|note|info), `confidence` (0..1),\n"
        "`file_path`, `begin_line`/`end_line`, and required `evidence` (verbatim "
        "substring from the source). Optional `rule_id`. Only report issues "
        "evidenced in the source. If none, return "
        '`"findings": []`. You may include a short `summary` string, but findings '
        "are authoritative.\n\n"
        f"Source:\n{_truncate(source, MAX_MODULE_CHARS)}"
    )
    return _system_analyst(), user


def build_project_synthesis_prompt(chunk_reports: Sequence[tuple[str, str]]) -> tuple[str, str]:
    """Final project-wide synthesis from per-module notes."""
    body_parts: list[str] = []
    for path, report in chunk_reports:
        body_parts.append(f"## {path}\n{_truncate(report, MAX_CHUNK_REPORT_CHARS)}")
    user = (
        "Synthesize a full-project analysis from the per-module notes below.\n"
        "Produce: architecture overview, cross-module coupling, hotspots, "
        "risk themes, and prioritized recommendations.\n"
        "Do not invent findings that contradict the structured notes.\n\n" + "\n\n".join(body_parts)
    )
    return _system_analyst(), user


def build_chat_prompt(
    message: str,
    *,
    history: Sequence[tuple[str, str]] = (),
    context_note: str = "",
) -> tuple[str, str]:
    """System + user prompts for on-demand chat."""
    system = (
        "You are a helpful Python coding assistant inside Codimension. "
        "Prefer concise, correct answers. Use markdown when useful."
    )
    lines: list[str] = []
    if context_note:
        lines.append("Context:\n" + context_note.strip())
        lines.append("")
    for role, text in history[-12:]:
        lines.append(f"{role.upper()}: {text}")
    lines.append(f"USER: {message}")
    lines.append("ASSISTANT:")
    return system, "\n".join(lines)


def _read_text_bounded(path: str, max_bytes: int) -> str:
    """Read at most ``max_bytes`` from ``path`` (UTF-8, replace errors)."""
    if max_bytes <= 0:
        return ""
    with open(path, "rb") as handle:
        raw = handle.read(max_bytes + 1)
    truncated = len(raw) > max_bytes
    if truncated:
        raw = raw[:max_bytes]
    text = raw.decode("utf-8", errors="replace")
    if truncated:
        text = text + "\n\n...[truncated: source byte budget]...\n"
    return text


def _invoke_complete(
    complete_fn: CompleteFn,
    system: str,
    user: str,
    *,
    max_output_tokens: int | None = None,
) -> str:
    """Call ``complete_fn``, passing ``max_output_tokens`` when supported."""
    if max_output_tokens is None:
        return str(complete_fn(system, user))
    try:
        signature = inspect.signature(complete_fn)
    except (TypeError, ValueError):
        signature = None
    if signature is not None:
        params = signature.parameters
        if "max_output_tokens" in params or any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
            return str(complete_fn(system, user, max_output_tokens=max_output_tokens))
    return str(complete_fn(system, user))


def _check_cancel_deadline(
    contract: AiJobContract,
    should_cancel: Optional[CancelCheck],
) -> None:
    """Raise when cancelled or past the job deadline."""
    if should_cancel is not None and should_cancel():
        raise AiTaskCancelled("AI task cancelled")
    if contract.deadline_exceeded():
        raise AiTaskDeadlineExceeded("AI task deadline exceeded")


def execute_ai_task(
    request: AiTaskRequest,
    complete_fn: CompleteFn,
    *,
    progress: Optional[ProgressFn] = None,
    backend_name: str = "http",
    budget_limits: Optional[AiBudgetLimits] = None,
    budget_environ: Optional[Mapping[str, str]] = None,
    job_contract: Optional[AiJobContract] = None,
    should_cancel: Optional[CancelCheck] = None,
) -> AiTaskResult:
    """Run ``request`` via ``complete_fn(system, user)`` and return text.

    ``budget_limits`` / ``budget_environ`` / ``job_contract`` apply to
    ``ANALYZE_PROJECT`` (R231 / R241). ``should_cancel`` is checked between
    provider calls.
    """

    def _progress(msg: str) -> None:
        if progress is not None:
            progress(msg)

    kind = request.kind
    if kind is AiTaskKind.ANALYZE_MODULE:
        if not (request.project_dir or "").strip() or not request.project_files:
            raise ValueError("Module analysis requires an open project context (project_dir + project .py file list).")
        module_path = assert_path_in_project(
            request.file_path,
            request.project_dir,
            request.project_files,
        )
        source = request.source or _read_text(module_path)
        ctx = build_project_module_context(
            module_path=module_path,
            source=source,
            project_dir=request.project_dir,
            project_files=request.project_files,
        )
        system, user = build_module_analysis_prompt(
            module_path,
            source,
            project_context_block=ctx.to_prompt_block(),
        )
        _progress(f"Analyzing module in project context: {ctx.module_relpath}…")
        text = _invoke_complete(complete_fn, system, user)
        return AiTaskResult(
            kind=kind,
            title=request.title,
            text=text,
            backend_name=backend_name,
            file_path=module_path,
        )

    if kind is AiTaskKind.ANALYZE_SYMBOL:
        pack = build_ai_context_from_source(
            request.source,
            request.symbol_name,
            file=request.file_path or "<memory>",
            kind=request.symbol_kind,
        )
        system, user = build_symbol_analysis_prompt(pack)
        _progress(f"Analyzing symbol {request.symbol_name}…")
        text = _invoke_complete(complete_fn, system, user)
        return AiTaskResult(
            kind=kind,
            title=request.title,
            text=text,
            backend_name=backend_name,
            file_path=request.file_path,
            symbol_name=request.symbol_name,
        )

    if kind is AiTaskKind.DOCSTRING:
        fragment, resolved_name = resolve_docstring_fragment(
            request.source,
            selected_text=request.selected_text,
            symbol_name=request.symbol_name,
            cursor_line=request.cursor_line,
        )
        symbol_name = resolved_name or request.symbol_name
        if not fragment:
            raise ValueError(
                "No code fragment for docstring: select a function/class (or place the cursor on its name)."
            )
        support = build_docstring_support_context(
            request.source,
            symbol_name=symbol_name,
            selected_fragment=fragment,
        )
        system, user = build_docstring_prompt(
            symbol_name=symbol_name,
            file_path=request.file_path or "<memory>",
            selected_fragment=fragment,
            support_context=support,
        )
        _progress(f"Generating docstring for {symbol_name or 'selection'}…")
        text = _invoke_complete(complete_fn, system, user).strip()
        if text.startswith('"""') or text.startswith("'''"):
            # Model sometimes wraps quotes — strip outer fences lightly.
            for q in ('"""', "'''"):
                if text.startswith(q) and text.endswith(q) and len(text) >= 6:
                    text = text[len(q) : -len(q)].strip()
                    break
        doc_target: Optional[DocstringTarget] = None
        if symbol_name or request.cursor_line:
            try:
                doc_target = build_docstring_target(
                    request.source,
                    file_path=request.file_path,
                    symbol_name=symbol_name,
                    cursor_line=request.cursor_line,
                )
                symbol_name = doc_target.symbol_name or symbol_name
            except ValueError:
                doc_target = None
        return AiTaskResult(
            kind=kind,
            title=request.title,
            text=text,
            backend_name=backend_name,
            file_path=request.file_path,
            symbol_name=symbol_name,
            docstring_target=doc_target,
        )

    if kind is AiTaskKind.CHAT:
        system, user = build_chat_prompt(
            request.chat_message,
            history=request.chat_history,
            context_note=request.source,
        )
        _progress("Chat…")
        text = _invoke_complete(complete_fn, system, user)
        return AiTaskResult(
            kind=kind,
            title=request.title or "AI Chat",
            text=text,
            backend_name=backend_name,
            file_path=request.file_path,
        )

    if kind is AiTaskKind.ANALYZE_PROJECT:
        return _execute_analyze_project(
            request,
            complete_fn,
            progress=_progress,
            backend_name=backend_name,
            budget_limits=budget_limits,
            budget_environ=budget_environ,
            job_contract=job_contract,
            should_cancel=should_cancel,
        )

    raise ValueError(f"unsupported AI task: {kind!r}")


def _execute_analyze_project(
    request: AiTaskRequest,
    complete_fn: CompleteFn,
    *,
    progress: ProgressFn,
    backend_name: str,
    budget_limits: Optional[AiBudgetLimits],
    budget_environ: Optional[Mapping[str, str]],
    job_contract: Optional[AiJobContract],
    should_cancel: Optional[CancelCheck],
) -> AiTaskResult:
    """Run project analysis with hard budgets, cancel, and audit findings (R241)."""
    files = list(request.project_files)
    if not files:
        raise ValueError("No Python files found in the project")

    if job_contract is not None:
        contract = job_contract
    else:
        limits = budget_limits if budget_limits is not None else load_ai_budget_limits(environ=budget_environ)
        contract = load_ai_job_contract(environ=budget_environ, limits=limits)

    if contract.max_files and len(files) > contract.max_files:
        files = files[: contract.max_files]
        progress(f"Capped project analysis to {contract.max_files} files (job contract)")

    tracker = AiBudgetTracker(limits=contract.limits)
    chunk_reports: list[tuple[str, str]] = []
    collected: list[AiFinding] = []
    total = len(files)
    analyzed = 0
    skipped = 0
    stopped = False
    requests_used = 0
    project_dir = (request.project_dir or "").strip()
    if not project_dir and files:
        project_dir = os.path.commonpath([os.path.abspath(p) for p in files])

    for index, path in enumerate(files, start=1):
        _check_cancel_deadline(contract, should_cancel)
        progress(f"Project analysis {index}/{total}: {path}")
        if contract.max_requests and requests_used >= contract.max_requests:
            stopped = True
            skipped = total - index + 1
            progress(f"AI request budget exhausted after {requests_used} requests")
            break
        try:
            source = _read_text_bounded(path, contract.max_source_bytes)
        except OSError as exc:
            chunk_reports.append((path, f"(unreadable: {exc})"))
            continue
        system, user = build_project_chunk_prompt(path, source, index, total)
        prompt_tokens = estimate_tokens(system) + estimate_tokens(user)
        # R249: provider cap = min(token remainder, cost remainder, contract max).
        out_cap = tracker.remaining_output_tokens(prompt_tokens, cap=contract.max_output_tokens)
        if out_cap <= 0 or not tracker.can_afford(prompt_tokens, out_cap):
            stopped = True
            skipped = total - index + 1
            progress(
                f"AI budget exhausted after {analyzed}/{total} files "
                f"(tokens≈{tracker.tokens_used}, cost≈${tracker.cost_usd:.4f})"
            )
            break
        report = _invoke_complete(complete_fn, system, user, max_output_tokens=out_cap)
        requests_used += 1
        try:
            tracker.record_texts(system + "\n" + user, report, hard=True)
        except AiBudgetExceeded:
            stopped = True
            skipped = total - index + 1
            progress("AI budget exceeded by provider response; discarding over-budget chunk")
            break
        chunk_reports.append((path, report))
        for finding in parse_findings_payload(report, default_file=path):
            audited = validate_audit_finding(
                finding,
                source=source,
                default_file=path,
                project_dir=project_dir,
                project_files=tuple(files) if not request.project_files else request.project_files,
            )
            if audited is not None:
                collected.append(audited)
        analyzed += 1

    synthesis = ""
    if chunk_reports and not stopped:
        _check_cancel_deadline(contract, should_cancel)
        if contract.max_requests and requests_used >= contract.max_requests:
            stopped = True
            progress("Skipping synthesis: request budget exhausted")
        else:
            progress("Synthesizing project-wide report…")
            system, user = build_project_synthesis_prompt(chunk_reports)
            prompt_tokens = estimate_tokens(system) + estimate_tokens(user)
            out_cap = tracker.remaining_output_tokens(prompt_tokens, cap=contract.max_output_tokens)
            if out_cap <= 0 or not tracker.can_afford(prompt_tokens, out_cap):
                stopped = True
                progress("Skipping synthesis: remaining AI budget insufficient")
            else:
                synthesis = _invoke_complete(complete_fn, system, user, max_output_tokens=out_cap)
                requests_used += 1
                try:
                    tracker.record_texts(system + "\n" + user, synthesis, hard=True)
                except AiBudgetExceeded:
                    synthesis = ""
                    stopped = True
                    progress("AI budget exceeded by synthesis response; discarding")

    findings = dedupe_findings(collected)
    findings_report = AiFindingsReport(
        findings=findings,
        tokens_used=tracker.tokens_used,
        cost_usd=tracker.cost_usd,
        stopped_by_budget=stopped,
        files_analyzed=analyzed,
        files_skipped=skipped,
    )
    header = f"# Project analysis ({analyzed}/{total} Python modules analyzed)\n\n{findings_report.to_markdown()}\n"
    if synthesis:
        body = header + "## Narrative synthesis\n\n" + synthesis
    else:
        body = header + ("## Narrative synthesis\n\n_(skipped or empty — see structured findings above)_\n")
    return AiTaskResult(
        kind=AiTaskKind.ANALYZE_PROJECT,
        title=request.title,
        text=body,
        backend_name=backend_name,
        findings=findings,
        findings_report=findings_report,
        budget_tokens_used=tracker.tokens_used,
        budget_cost_usd=tracker.cost_usd,
        budget_stopped=stopped,
    )


__all__ = [
    "AiTaskCancelled",
    "AiTaskDeadlineExceeded",
    "AiTaskKind",
    "AiTaskRequest",
    "AiTaskResult",
    "DOCSTRING_STYLE",
    "CompleteFn",
    "execute_ai_task",
    "list_project_py_files",
    "build_project_chunk_prompt",
    "build_project_synthesis_prompt",
]
