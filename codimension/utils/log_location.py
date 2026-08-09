# -*- coding: utf-8 -*-
"""Parse file:line locations from IDE log messages (R177)."""

from __future__ import annotations

import os
import re

# POSIX /path/file.py:42: msg  or  /path/file.py:42 msg
_RE_COLON = re.compile(
    r"(?P<path>(?:[A-Za-z]:)?[/\\][^\s:]+|[^\s:]+[/\\][^\s:]+|[^\s:]+\.(?:py|pyw|pyi))"
    r":(?P<line>\d+)(?::|\s|$)"
)
# File "path", line N
_RE_TRACEBACK = re.compile(r'File "(?P<path>[^"]+)", line (?P<line>\d+)')
# path(line):  e.g. pylint-style
_RE_PARENS = re.compile(
    r"(?P<path>(?:[A-Za-z]:)?[/\\][^\s(]+|[^\s(]+[/\\][^\s(]+|[^\s(]+\.(?:py|pyw|pyi))"
    r"\((?P<line>\d+)\):"
)
# /path/file.py ... at line N  (import-diagram style without path:line: prefix)
_RE_AT_LINE = re.compile(
    r"(?P<path>(?:[A-Za-z]:)?[/\\][^\s:]+\.(?:py|pyw|pyi)|[^\s:]+\.(?:py|pyw|pyi))"
    r".*?\bat line (?P<line>\d+)\b"
)


def _match_location(match, *, require_existing: bool) -> tuple[str, int] | None:
    """Validate a regex match and return ``(path, line)`` or ``None``."""
    path = match.group("path").strip()
    try:
        line = int(match.group("line"))
    except (TypeError, ValueError):
        return None
    if line < 1 or not path:
        return None
    # Skip obvious non-paths (timestamps like 2026-08-09, log levels)
    if path.upper() in ("WARNING", "ERROR", "CRITICAL", "INFO", "DEBUG"):
        return None
    if require_existing:
        if not os.path.isfile(path):
            # Relative path: try as-is only; callers pass absolute paths in logs.
            return None
        path = os.path.abspath(path)
    return path, line


def parse_log_location(text: str, *, require_existing: bool = True) -> tuple[str, int] | None:
    """Extract ``(absolute_or_given_path, line)`` from a log line, or ``None``.

    Recognizes ``path:line:``, ``path:line``, ``File "path", line N``,
    ``path(line):``, and ``path ... at line N``. When ``require_existing`` is
    True (default), the path must exist and be a file. ``line`` must be ``>= 1``.
    """
    if not text or not text.strip():
        return None

    for pattern in (_RE_TRACEBACK, _RE_PARENS, _RE_COLON, _RE_AT_LINE):
        match = pattern.search(text)
        if not match:
            continue
        loc = _match_location(match, require_existing=require_existing)
        if loc is not None:
            return loc
    return None
