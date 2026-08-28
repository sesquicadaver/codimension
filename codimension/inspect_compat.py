# -*- coding: utf-8 -*-
#
# codimension - graphics python two-way code editor and analyzer
# Copyright (C) 2026  Codimension Team
# The license is described in the LICENSE file at the root directory.
#

"""Restore ``inspect.formatargspec`` so wrapt 1.12 (astroid 2.5) imports on 3.11+.

``cdmpylintplugin`` pins ``pylint==2.5.3`` → ``astroid==2.5`` → ``wrapt<1.13``.
That wrapt release does ``from inspect import formatargspec``, which was removed
in Python 3.11. R197 keeps ``wrapt==1.12.1`` in ``constraints.txt`` (so
``pip install -c`` resolves) and applies this shim instead of a manual
``pip install wrapt>=1.14 --no-deps`` override.
"""

from __future__ import annotations

import inspect
import types
from typing import Any, Callable, Mapping, Sequence


def _formatannotation(annotation: Any, base_module: str | None = None) -> str:
    """Format a single annotation (CPython 3.10 ``inspect.formatannotation``)."""
    if getattr(annotation, "__module__", None) == "typing":
        return repr(annotation).replace("typing.", "")
    if isinstance(annotation, types.GenericAlias):
        return str(annotation)
    if isinstance(annotation, type):
        if annotation.__module__ in ("builtins", base_module):
            return annotation.__qualname__
        return annotation.__module__ + "." + annotation.__qualname__
    return repr(annotation)


def formatargspec(
    args: Sequence[str],
    varargs: str | None = None,
    varkw: str | None = None,
    defaults: Sequence[Any] | None = None,
    kwonlyargs: Sequence[str] = (),
    kwonlydefaults: Mapping[str, Any] | None = None,
    annotations: Mapping[str, Any] | None = None,
    formatarg: Callable[[str], str] = str,
    formatvarargs: Callable[[str], str] = lambda name: "*" + name,
    formatvarkw: Callable[[str], str] = lambda name: "**" + name,
    formatvalue: Callable[[Any], str] = lambda value: "=" + repr(value),
    formatreturns: Callable[[str], str] = lambda text: " -> " + text,
    formatannotation: Callable[..., str] = _formatannotation,
) -> str:
    """Format an argument spec (legacy API required by wrapt 1.12)."""
    if kwonlydefaults is None:
        kwonlydefaults = {}
    if annotations is None:
        annotations = {}

    def formatargandannotation(arg: str) -> str:
        result = formatarg(arg)
        if arg in annotations:
            result += ": " + formatannotation(annotations[arg])
        return result

    specs: list[str] = []
    firstdefault = 0
    if defaults:
        firstdefault = len(args) - len(defaults)
    for i, arg in enumerate(args):
        spec = formatargandannotation(arg)
        if defaults and i >= firstdefault:
            spec = spec + formatvalue(defaults[i - firstdefault])
        specs.append(spec)
    if varargs is not None:
        specs.append(formatvarargs(formatargandannotation(varargs)))
    elif kwonlyargs:
        specs.append("*")
    for kwonlyarg in kwonlyargs:
        spec = formatargandannotation(kwonlyarg)
        if kwonlyarg in kwonlydefaults:
            spec += formatvalue(kwonlydefaults[kwonlyarg])
        specs.append(spec)
    if varkw is not None:
        specs.append(formatvarkw(formatargandannotation(varkw)))
    result = "(" + ", ".join(specs) + ")"
    if "return" in annotations:
        result += formatreturns(formatannotation(annotations["return"]))
    return result


def ensure_wrapt_compat() -> bool:
    """Install ``inspect.formatargspec`` when missing; return True if patched."""
    if hasattr(inspect, "formatargspec"):
        return False
    setattr(inspect, "formatargspec", formatargspec)
    return True
