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


def parse_log_location(text: str, *, require_existing: bool = True) -> tuple[str, int] | None:
    """Extract ``(absolute_or_given_path, line)`` from a log line, or ``None``.

    Recognizes ``path:line:``, ``path:line``, ``File "path", line N``, and
    ``path(line):``. When ``require_existing`` is True (default), the path must
    exist and be a file. ``line`` must be ``>= 1``.
    """
    if not text or not text.strip():
        return None

    for pattern in (_RE_TRACEBACK, _RE_PARENS, _RE_COLON):
        match = pattern.search(text)
        if not match:
            continue
        path = match.group("path").strip()
        try:
            line = int(match.group("line"))
        except (TypeError, ValueError):
            continue
        if line < 1 or not path:
            continue
        # Skip obvious non-paths (timestamps like 2026-08-09, log levels)
        if path.upper() in ("WARNING", "ERROR", "CRITICAL", "INFO", "DEBUG"):
            continue
        if require_existing:
            if not os.path.isfile(path):
                # Relative path: try as-is only; callers pass absolute paths in logs.
                continue
            path = os.path.abspath(path)
        return path, line
    return None
