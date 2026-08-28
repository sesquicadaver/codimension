# -*- coding: utf-8 -*-
#
# codimension - MCP auth (R182)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Fail-closed token gate for the MCP backend (R182).

Startup requires a non-empty ``CDM_MCP_TOKEN``. After that, stdio transport is
process-local trust; optional per-call checks use ``hmac.compare_digest``.
"""

from __future__ import annotations

import hmac
import os
import sys
from typing import Mapping, Optional

#: Environment variable holding the shared secret for MCP process startup.
MCP_TOKEN_ENV = "CDM_MCP_TOKEN"


class AuthError(RuntimeError):
    """Raised when MCP auth requirements are not met."""


def read_token(environ: Optional[Mapping[str, str]] = None) -> str:
    """Return the configured token string (may be empty).

    When ``environ`` is passed, only that mapping is consulted (tests).
    """
    env: Mapping[str, str] = os.environ if environ is None else environ
    raw = env.get(MCP_TOKEN_ENV, "")
    if raw is None:
        return ""
    return str(raw)


def require_startup_token(environ: Optional[Mapping[str, str]] = None) -> str:
    """Return a non-empty token or raise :class:`AuthError` (fail-closed)."""
    token = read_token(environ).strip()
    if not token:
        raise AuthError(f"{MCP_TOKEN_ENV} must be set to a non-empty value before starting the MCP server")
    return token


def tokens_match(expected: str, provided: Optional[str]) -> bool:
    """Constant-time equality for optional per-call token checks."""
    if provided is None:
        return False
    left = expected.encode("utf-8")
    right = str(provided).encode("utf-8")
    if len(left) != len(right):
        # compare_digest requires equal length; still do a dummy compare.
        return hmac.compare_digest(left, left) and False
    return hmac.compare_digest(left, right)


def verify_call_token(expected: str, provided: Optional[str]) -> None:
    """Raise :class:`AuthError` when an optional call token does not match."""
    if not tokens_match(expected, provided):
        raise AuthError("MCP call token mismatch")


def require_startup_token_or_exit(environ: Optional[Mapping[str, str]] = None) -> str:
    """CLI helper: print to stderr and exit 1 when the token is missing."""
    try:
        return require_startup_token(environ)
    except AuthError as exc:
        sys.stderr.write(f"codimension-mcp: {exc}\n")
        raise SystemExit(1) from exc


__all__ = [
    "AuthError",
    "MCP_TOKEN_ENV",
    "read_token",
    "require_startup_token",
    "require_startup_token_or_exit",
    "tokens_match",
    "verify_call_token",
]
