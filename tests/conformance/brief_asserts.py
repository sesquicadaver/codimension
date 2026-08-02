# -*- coding: utf-8 -*-
"""Helpers for brief_ast conformance assertions (T006)."""

from __future__ import annotations

import importlib.util
import os.path
from typing import Any


def _load_brief_ast() -> Any:
    path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "codimension",
        "parsers",
        "brief_ast.py",
    )
    spec = importlib.util.spec_from_file_location("brief_ast_conformance", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


_brief = _load_brief_ast()
getBriefModuleInfoFromMemory = _brief.getBriefModuleInfoFromMemory


def parse_brief(source: str) -> Any:
    """Parse source into brief module info."""
    return getBriefModuleInfoFromMemory(source)


def function_names(info: Any, *, async_only: bool | None = None) -> list[str]:
    """Top-level function names, optionally filtered by isAsync."""
    out: list[str] = []
    for fn in info.functions:
        if async_only is True and not getattr(fn, "isAsync", False):
            continue
        if async_only is False and getattr(fn, "isAsync", False):
            continue
        out.append(fn.name)
    return out


def class_method_names(info: Any, class_name: str) -> list[str]:
    """Method names for a top-level class."""
    for cls in info.classes:
        if cls.name == class_name:
            return [fn.name for fn in cls.functions]
    return []


def argument_defaults(info: Any, func_name: str) -> dict[str, str | None]:
    """Map argument name → default value string (or None) for a top-level function."""
    for fn in info.functions:
        if fn.name != func_name:
            continue
        result: dict[str, str | None] = {}
        for arg in fn.arguments:
            result[arg.name] = arg.value
        return result
    return {}


def instance_attribute_names(info: Any, class_name: str) -> list[str]:
    """Instance attribute names collected for a class."""
    for cls in info.classes:
        if cls.name == class_name:
            return [a.name for a in cls.instanceAttributes]
    return []


def class_attribute_names(info: Any, class_name: str) -> list[str]:
    """Class attribute names collected for a class."""
    for cls in info.classes:
        if cls.name == class_name:
            return [a.name for a in cls.classAttributes]
    return []


def global_names(info: Any) -> list[str]:
    """Module-level global names."""
    return [g.name for g in info.globals]
