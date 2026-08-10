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
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterable, Optional, Sequence

from core.ai_context import AiContextPack, build_ai_context_from_source
from core.symbol_index import SymbolKind

CompleteFn = Callable[[str, str], str]
ProgressFn = Callable[[str], None]

MAX_MODULE_CHARS = 12000
MAX_CHUNK_REPORT_CHARS = 6000
DOCSTRING_STYLE = "Google"


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
    chat_message: str = ""
    chat_history: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class AiTaskResult:
    """Text result for the AI Result / Chat panel."""

    kind: AiTaskKind
    title: str
    text: str
    backend_name: str
    file_path: str = ""
    symbol_name: str = ""


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
        "Do not invent APIs that are not in the provided source."
    )


def _system_docstring() -> str:
    return (
        "You write Google-style Python docstrings only. "
        "Return ONLY the docstring body suitable to place inside triple quotes "
        "(no surrounding quotes, no code fences, no prose outside the docstring). "
        "Include Args / Returns / Raises sections when applicable."
    )


def build_module_analysis_prompt(path: str, source: str) -> tuple[str, str]:
    """System + user prompts for module analysis."""
    user = (
        f"Analyze this Python module end-to-end.\n"
        f"File: {path}\n\n"
        f"Cover: purpose, public API, key types/functions, control-flow risks, "
        f"coupling, and concrete improvement suggestions.\n\n"
        f"Source:\n{_truncate(source, MAX_MODULE_CHARS)}"
    )
    return _system_analyst(), user


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


def build_docstring_prompt(pack: AiContextPack) -> tuple[str, str]:
    """System + user prompts for a Google-style docstring."""
    user = (
        f"Write a {DOCSTRING_STYLE}-style docstring for this symbol.\n"
        f"Symbol: {pack.symbol.qualname or pack.symbol.name} ({pack.symbol.kind.value})\n"
        f"File: {pack.symbol.file}\n\n"
        f"Source:\n{_truncate(pack.source_excerpt, MAX_MODULE_CHARS)}"
    )
    return _system_docstring(), user


def build_project_chunk_prompt(path: str, source: str, index: int, total: int) -> tuple[str, str]:
    """Per-file project analysis chunk."""
    user = (
        f"Project analysis chunk {index}/{total}.\n"
        f"Summarize this module for a later project-wide synthesis "
        f"(purpose, public API, risks, notable couplings).\n"
        f"File: {path}\n\n"
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
        "risk themes, and prioritized recommendations.\n\n" + "\n\n".join(body_parts)
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


def execute_ai_task(
    request: AiTaskRequest,
    complete_fn: CompleteFn,
    *,
    progress: Optional[ProgressFn] = None,
    backend_name: str = "http",
) -> AiTaskResult:
    """Run ``request`` via ``complete_fn(system, user)`` and return text."""

    def _progress(msg: str) -> None:
        if progress is not None:
            progress(msg)

    kind = request.kind
    if kind is AiTaskKind.ANALYZE_MODULE:
        source = request.source or _read_text(request.file_path)
        system, user = build_module_analysis_prompt(request.file_path or "<module>", source)
        _progress(f"Analyzing module {request.file_path or ''}…")
        text = complete_fn(system, user)
        return AiTaskResult(
            kind=kind,
            title=request.title,
            text=text,
            backend_name=backend_name,
            file_path=request.file_path,
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
        text = complete_fn(system, user)
        return AiTaskResult(
            kind=kind,
            title=request.title,
            text=text,
            backend_name=backend_name,
            file_path=request.file_path,
            symbol_name=request.symbol_name,
        )

    if kind is AiTaskKind.DOCSTRING:
        pack = build_ai_context_from_source(
            request.source,
            request.symbol_name,
            file=request.file_path or "<memory>",
            kind=request.symbol_kind,
        )
        system, user = build_docstring_prompt(pack)
        _progress(f"Generating docstring for {request.symbol_name}…")
        text = complete_fn(system, user).strip()
        if text.startswith('"""') or text.startswith("'''"):
            # Model sometimes wraps quotes — strip outer fences lightly.
            for q in ('"""', "'''"):
                if text.startswith(q) and text.endswith(q) and len(text) >= 6:
                    text = text[len(q) : -len(q)].strip()
                    break
        return AiTaskResult(
            kind=kind,
            title=request.title,
            text=text,
            backend_name=backend_name,
            file_path=request.file_path,
            symbol_name=request.symbol_name,
        )

    if kind is AiTaskKind.CHAT:
        system, user = build_chat_prompt(
            request.chat_message,
            history=request.chat_history,
            context_note=request.source,
        )
        _progress("Chat…")
        text = complete_fn(system, user)
        return AiTaskResult(
            kind=kind,
            title=request.title or "AI Chat",
            text=text,
            backend_name=backend_name,
            file_path=request.file_path,
        )

    if kind is AiTaskKind.ANALYZE_PROJECT:
        files = list(request.project_files)
        if not files:
            raise ValueError("No Python files found in the project")
        chunk_reports: list[tuple[str, str]] = []
        total = len(files)
        for index, path in enumerate(files, start=1):
            _progress(f"Project analysis {index}/{total}: {path}")
            try:
                source = _read_text(path)
            except OSError as exc:
                chunk_reports.append((path, f"(unreadable: {exc})"))
                continue
            system, user = build_project_chunk_prompt(path, source, index, total)
            report = complete_fn(system, user)
            chunk_reports.append((path, report))
        _progress("Synthesizing project-wide report…")
        system, user = build_project_synthesis_prompt(chunk_reports)
        text = complete_fn(system, user)
        header = f"# Project analysis ({total} Python modules)\n\n"
        return AiTaskResult(
            kind=kind,
            title=request.title,
            text=header + text,
            backend_name=backend_name,
        )

    raise ValueError(f"unsupported AI task: {kind!r}")


__all__ = [
    "AiTaskKind",
    "AiTaskRequest",
    "AiTaskResult",
    "DOCSTRING_STYLE",
    "CompleteFn",
    "execute_ai_task",
    "list_project_py_files",
]
