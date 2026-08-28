# -*- coding: utf-8 -*-
"""Codimension package root — apply early runtime compat shims (R197)."""

from __future__ import annotations

try:
    from .inspect_compat import ensure_wrapt_compat
except ImportError:  # pragma: no cover - flat layout / editable edge
    from inspect_compat import ensure_wrapt_compat  # type: ignore[no-redef]

ensure_wrapt_compat()
