# -*- coding: utf-8 -*-
#
# codimension - static plugin policy (R220)
# Copyright (C) 2026  Codimension Team
# The license is described in the LICENSE file at the root directory.
#

"""Fail-closed static plugin policy evaluated before importing plugin code.

R220 / audit P1-16: parse ``.cdmp`` (+ lightweight source heuristics) and reject
incompatible candidates before ``yapsy`` executes plugin modules.
"""

from __future__ import annotations

import ast
import configparser
import os
import re
from dataclasses import dataclass
from typing import Optional

from packaging.version import InvalidVersion, Version
from plugins.capabilities import (
    HOST_CAPABILITIES,
    HOST_PLUGIN_API_VERSION,
    PluginCapabilitySpec,
    negotiate_plugin_capabilities,
)

# Keep in sync with plugins.manager.pluginmanager.CATEGORIES
KNOWN_CATEGORIES = frozenset({"VersionControlSystemInterface", "WizardInterface"})

_VERSION_GE_RE = re.compile(
    r"""Version\(\s*ideVersion\s*\)\s*>=\s*Version\(\s*['\"]([^'\"]+)['\"]\s*\)""",
    re.MULTILINE,
)


@dataclass(frozen=True)
class StaticPluginPolicy:
    """Manifest / source-derived requirements used before import."""

    name: str = ""
    version: str = "0"
    category: Optional[str] = None
    min_ide_version: Optional[str] = None
    capability_spec: Optional[PluginCapabilitySpec] = None
    source_path: str = ""
    info_path: str = ""


@dataclass(frozen=True)
class StaticPolicyDecision:
    """Outcome of evaluating :class:`StaticPluginPolicy` against the host."""

    ok: bool
    reason: str = ""
    # Conflict codes match CDMPluginManager constants (imported lazily by callers).
    conflict_code: int = 0


def _read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def resolve_plugin_source_path(module_filepath: str) -> str:
    """Best-effort ``.py`` path for a yapsy module filepath."""
    candidates: list[str] = []
    base = module_filepath or ""
    if base.endswith("__init__"):
        candidates.append(base + ".py")
        candidates.append(os.path.join(os.path.dirname(base), "__init__.py"))
    else:
        candidates.append(base + ".py")
        candidates.append(base)
        candidates.append(os.path.join(base, "__init__.py"))
    for path in candidates:
        if os.path.isfile(path):
            return path
    return ""


def guess_category_from_text(text: str) -> Optional[str]:
    """Infer category from source text without importing."""
    if not text:
        return None
    if "VersionControlSystemInterface" in text:
        return "VersionControlSystemInterface"
    if "WizardInterface" in text:
        return "WizardInterface"
    return None


def _parse_capability_call(node: ast.Call) -> Optional[PluginCapabilitySpec]:
    """Build a :class:`PluginCapabilitySpec` from an AST ``Call`` when possible."""
    func = node.func
    name = ""
    if isinstance(func, ast.Name):
        name = func.id
    elif isinstance(func, ast.Attribute):
        name = func.attr
    if name != "PluginCapabilitySpec":
        return None

    kwargs: dict[str, object] = {}
    for keyword in node.keywords:
        if keyword.arg is None:
            continue
        value = keyword.value
        if keyword.arg in {"min_api_version", "max_api_version"}:
            if isinstance(value, ast.Constant) and isinstance(value.value, int):
                kwargs[keyword.arg] = value.value
            continue
        if keyword.arg in {"required", "optional"}:
            items: set[str] = set()
            # frozenset({...}) / set({...}) / {...}
            target = value
            if isinstance(value, ast.Call) and isinstance(value.func, (ast.Name, ast.Attribute)):
                call_name = value.func.id if isinstance(value.func, ast.Name) else value.func.attr
                if call_name in {"frozenset", "set"} and value.args:
                    target = value.args[0]
            if isinstance(target, (ast.Set, ast.Tuple, ast.List)):
                for elt in target.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        items.add(elt.value)
            kwargs[keyword.arg] = frozenset(items)
    try:
        min_api_raw = kwargs.get("min_api_version", 1)
        max_api_raw = kwargs.get("max_api_version")
        required_raw = kwargs.get("required", frozenset())
        optional_raw = kwargs.get("optional", frozenset())
        if not isinstance(min_api_raw, int):
            return None
        if max_api_raw is not None and not isinstance(max_api_raw, int):
            return None
        if not isinstance(required_raw, frozenset) or not isinstance(optional_raw, frozenset):
            return None
        return PluginCapabilitySpec(
            min_api_version=min_api_raw,
            max_api_version=max_api_raw,
            required=required_raw,
            optional=optional_raw,
        )
    except (TypeError, ValueError):
        return None


def extract_capability_spec_from_source(text: str) -> Optional[PluginCapabilitySpec]:
    """Return ``PluginCapabilitySpec(...)`` found under ``getCapabilityRequirements``."""
    if not text or "PluginCapabilitySpec" not in text:
        return None
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != "getCapabilityRequirements":
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                spec = _parse_capability_call(child)
                if spec is not None:
                    return spec
    # Fallback: any PluginCapabilitySpec(...) in the module.
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            spec = _parse_capability_call(node)
            if spec is not None:
                return spec
    return None


def extract_min_ide_version_from_source(text: str) -> Optional[str]:
    """Extract ``Version(ideVersion) >= Version('X')`` floor from source text."""
    if not text:
        return None
    match = _VERSION_GE_RE.search(text)
    if match:
        return match.group(1)
    return None


def _parse_cdmp_policy(info_path: str) -> dict[str, str]:
    """Return ``[Codimension]`` keys from a ``.cdmp`` file (empty if absent)."""
    if not info_path or not os.path.isfile(info_path):
        return {}
    parser = configparser.ConfigParser()
    try:
        parser.read(info_path, encoding="utf-8")
    except (OSError, configparser.Error):
        return {}
    if not parser.has_section("Codimension"):
        return {}
    return {key: value.strip() for key, value in parser.items("Codimension")}


def _spec_from_manifest(keys: dict[str, str]) -> Optional[PluginCapabilitySpec]:
    if not any(k in keys for k in ("minpluginapi", "maxpluginapi", "requiredcapabilities")):
        return None
    required_raw = keys.get("requiredcapabilities", "")
    required = frozenset(part.strip() for part in required_raw.split(",") if part.strip())
    min_api = int(keys.get("minpluginapi", "1") or "1")
    max_raw = keys.get("maxpluginapi", "").strip()
    max_api: Optional[int] = int(max_raw) if max_raw else None
    return PluginCapabilitySpec(min_api_version=min_api, max_api_version=max_api, required=required)


def build_static_plugin_policy(
    *,
    info_path: str,
    module_filepath: str,
    name: str = "",
    version: str = "0",
) -> StaticPluginPolicy:
    """Combine ``.cdmp`` ``[Codimension]`` keys with source heuristics."""
    source_path = resolve_plugin_source_path(module_filepath)
    text = _read_text(source_path) if source_path else ""
    keys = {k.lower(): v for k, v in _parse_cdmp_policy(info_path).items()}

    category = keys.get("category") or guess_category_from_text(text)
    if category and category not in KNOWN_CATEGORIES:
        category = None

    min_ide = keys.get("minideversion") or extract_min_ide_version_from_source(text)
    spec = _spec_from_manifest(keys)
    if spec is None:
        spec = extract_capability_spec_from_source(text)

    return StaticPluginPolicy(
        name=name or "",
        version=version or "0",
        category=category,
        min_ide_version=min_ide,
        capability_spec=spec,
        source_path=source_path,
        info_path=info_path or "",
    )


def evaluate_static_plugin_policy(
    policy: StaticPluginPolicy,
    *,
    ide_version: str,
    host_api_version: int = HOST_PLUGIN_API_VERSION,
    host_capabilities: frozenset[str] = HOST_CAPABILITIES,
    # Conflict codes (CDMPluginManager): BAD_BASE_CLASS=4, INCOMPATIBLE_IDE=2, CAPABILITIES=8
    bad_base_class: int = 4,
    incompatible_ide: int = 2,
    incompatible_capabilities: int = 8,
) -> StaticPolicyDecision:
    """Fail-closed policy gate used before importing a plugin module."""
    if not policy.category:
        return StaticPolicyDecision(
            ok=False,
            reason="plugin category could not be determined before import (fail-closed)",
            conflict_code=bad_base_class,
        )
    if policy.category not in KNOWN_CATEGORIES:
        return StaticPolicyDecision(
            ok=False,
            reason=f"unknown plugin category {policy.category!r}",
            conflict_code=bad_base_class,
        )

    if policy.min_ide_version:
        try:
            if Version(ide_version) < Version(policy.min_ide_version):
                return StaticPolicyDecision(
                    ok=False,
                    reason=(f"IDE version {ide_version} is older than plugin minimum {policy.min_ide_version}"),
                    conflict_code=incompatible_ide,
                )
        except InvalidVersion:
            return StaticPolicyDecision(
                ok=False,
                reason=f"invalid IDE/plugin version for comparison ({ide_version!r})",
                conflict_code=incompatible_ide,
            )

    result = negotiate_plugin_capabilities(
        policy.capability_spec,
        host_api_version=host_api_version,
        host_capabilities=host_capabilities,
    )
    if not result.ok:
        return StaticPolicyDecision(
            ok=False,
            reason=result.reason,
            conflict_code=incompatible_capabilities,
        )

    return StaticPolicyDecision(ok=True, reason="accepted")


__all__ = [
    "KNOWN_CATEGORIES",
    "StaticPluginPolicy",
    "StaticPolicyDecision",
    "build_static_plugin_policy",
    "evaluate_static_plugin_policy",
    "extract_capability_spec_from_source",
    "extract_min_ide_version_from_source",
    "guess_category_from_text",
    "resolve_plugin_source_path",
]
