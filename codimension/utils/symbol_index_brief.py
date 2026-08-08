# -*- coding: utf-8 -*-
#
# codimension - graphics python two-way code editor and analyzer
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Populate ``core.symbol_index.SymbolIndex`` from ``brief_ast`` (R131).

Async-friendly: ``build_symbol_index`` accepts an optional ``on_file`` callback
so callers can drive work from a worker thread / event loop without this module
importing Qt or asyncio.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import Optional

from core.symbol_index import SourceSpan, SymbolIndex, SymbolKind, SymbolRecord
from parsers.brief_ast import (
    BriefModuleInfo,
    Class,
    Function,
    getBriefModuleInfoFromFile,
    getBriefModuleInfoFromMemory,
)


def _span_for_name(obj: object) -> SourceSpan:
    """Half-open span covering the identifier at ``absPosition``."""
    name = str(getattr(obj, "name", "") or "")
    start = int(getattr(obj, "absPosition", 0) or 0)
    if start < 0:
        start = 0
    return SourceSpan(start, start + len(name))


def _line_for(obj: object) -> Optional[int]:
    """Return 1-based brief_ast line when present."""
    line = getattr(obj, "line", None)
    if line is None:
        return None
    try:
        value = int(line)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _emit_function(
    out: list[SymbolRecord],
    func: Function,
    file: str,
    container: Optional[str],
    *,
    as_method: bool,
) -> None:
    """Append a function/method and nested defs/classes."""
    kind = SymbolKind.METHOD if as_method else SymbolKind.FUNCTION
    rec = SymbolRecord(
        name=func.name,
        kind=kind,
        file=file,
        span=_span_for_name(func),
        container=container,
        line=_line_for(func),
    )
    out.append(rec)
    nested_container = rec.qualname
    for nested in func.functions:
        _emit_function(out, nested, file, nested_container, as_method=False)
    for nested_cls in func.classes:
        _emit_class(out, nested_cls, file, nested_container)


def _emit_class(
    out: list[SymbolRecord],
    cls: Class,
    file: str,
    container: Optional[str],
) -> None:
    """Append a class, its attributes, methods, and nested classes."""
    rec = SymbolRecord(
        name=cls.name,
        kind=SymbolKind.CLASS,
        file=file,
        span=_span_for_name(cls),
        container=container,
        line=_line_for(cls),
    )
    out.append(rec)
    qn = rec.qualname
    for attr in cls.classAttributes:
        out.append(
            SymbolRecord(
                name=attr.name,
                kind=SymbolKind.ATTRIBUTE,
                file=file,
                span=_span_for_name(attr),
                container=qn,
                line=_line_for(attr),
            )
        )
    for attr in cls.instanceAttributes:
        out.append(
            SymbolRecord(
                name=attr.name,
                kind=SymbolKind.ATTRIBUTE,
                file=file,
                span=_span_for_name(attr),
                container=qn,
                line=_line_for(attr),
                extras={"scope": "instance"},
            )
        )
    for func in cls.functions:
        _emit_function(out, func, file, qn, as_method=True)
    for nested in cls.classes:
        _emit_class(out, nested, file, qn)


def symbols_from_brief(info: BriefModuleInfo, file: str) -> list[SymbolRecord]:
    """Convert a parsed ``BriefModuleInfo`` into symbol records for ``file``."""
    out: list[SymbolRecord] = []
    for imp in info.imports:
        out.append(
            SymbolRecord(
                name=imp.name,
                kind=SymbolKind.IMPORT,
                file=file,
                span=_span_for_name(imp),
                container=None,
                line=_line_for(imp),
            )
        )
        for what in imp.what:
            out.append(
                SymbolRecord(
                    name=what.name,
                    kind=SymbolKind.IMPORT,
                    file=file,
                    span=_span_for_name(what),
                    container=None,
                    line=_line_for(what),
                    extras={"from": imp.name},
                )
            )
    for glob in info.globals:
        out.append(
            SymbolRecord(
                name=glob.name,
                kind=SymbolKind.VARIABLE,
                file=file,
                span=_span_for_name(glob),
                container=None,
                line=_line_for(glob),
            )
        )
    for func in info.functions:
        _emit_function(out, func, file, None, as_method=False)
    for cls in info.classes:
        _emit_class(out, cls, file, None)
    return out


def index_source(source: str, file: str) -> list[SymbolRecord]:
    """Parse ``source`` with brief_ast and return symbol records."""
    info = getBriefModuleInfoFromMemory(source, file)
    if not info.isOK:
        return []
    return symbols_from_brief(info, file)


def index_file(path: str) -> list[SymbolRecord]:
    """Parse a file with brief_ast and return symbol records."""
    info = getBriefModuleInfoFromFile(path)
    if not info.isOK:
        return []
    return symbols_from_brief(info, path)


def build_symbol_index(
    paths: Sequence[str] | Iterable[str],
    *,
    on_file: Optional[Callable[[str, Sequence[SymbolRecord]], None]] = None,
) -> SymbolIndex:
    """Build a ``SymbolIndex`` for the given project file paths.

    ``on_file(path, records)`` is invoked after each file (sync). Callers that
    need cooperative scheduling can pass a callback that yields to their loop.
    """
    index = SymbolIndex()
    for path in paths:
        records = index_file(path)
        index.extend(records)
        if on_file is not None:
            on_file(path, records)
    return index


def build_symbol_index_from_sources(
    items: Sequence[tuple[str, str]],
    *,
    on_file: Optional[Callable[[str, Sequence[SymbolRecord]], None]] = None,
) -> SymbolIndex:
    """Build an index from ``(file, source)`` pairs (tests / in-memory projects)."""
    index = SymbolIndex()
    for file, source in items:
        records = index_source(source, file)
        index.extend(records)
        if on_file is not None:
            on_file(file, records)
    return index


__all__ = [
    "build_symbol_index",
    "build_symbol_index_from_sources",
    "index_file",
    "index_source",
    "symbols_from_brief",
]
