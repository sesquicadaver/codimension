# -*- coding: utf-8 -*-
#
# codimension - static plugin policy (R220 / R225)
# Copyright (C) 2026  Codimension Team
# The license is described in the LICENSE file at the root directory.
#

"""Fail-closed static plugin policy evaluated before importing plugin code.

R220 / audit P1-16: parse ``.cdmp`` (+ lightweight source heuristics) and reject
incompatible candidates before ``yapsy`` executes plugin modules.

R225 / audit P1-07: third-party plugins require a complete ``[Codimension]``
manifest block (category, API, capabilities, min IDE, entrypoint). Unknown or
invalid manifests are denied — no legacy import fallback.
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

#: Keys required under ``[Codimension]`` for third-party plugins (R225).
REQUIRED_MANIFEST_KEYS = frozenset(
    {
        "category",
        "minideversion",
        "minpluginapi",
        "requiredcapabilities",
        "entrypoint",
    }
)

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
    entrypoint: str = ""
    require_manifest: bool = False
    manifest_error: str = ""


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


def is_trusted_bundled_plugin_path(path: str) -> bool:
    """True when ``path`` lives under the shipped ``cdmplugins`` package tree."""
    text = (path or "").strip()
    if not text:
        return False
    try:
        import cdmplugins
    except Exception:
        return False
    root = os.path.realpath(os.path.dirname(os.path.abspath(cdmplugins.__file__)))
    real = os.path.realpath(os.path.expanduser(text))
    root_sep = root if root.endswith(os.sep) else root + os.sep
    return real == root or real.startswith(root_sep)


def guess_category_from_text(text: str) -> Optional[str]:
    """Infer category from source text without importing (bundled/legacy only)."""
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


def _parse_cdmp_sections(info_path: str) -> tuple[dict[str, str], dict[str, str], str]:
    """Return ``(core_keys, codimension_keys, error)`` from a ``.cdmp`` file.

    Errors are candidate-local (invalid file / section) and never raise.
    """
    if not info_path or not os.path.isfile(info_path):
        return {}, {}, "plugin .cdmp info file is missing"
    parser = configparser.ConfigParser()
    try:
        read_ok = parser.read(info_path, encoding="utf-8")
    except (OSError, configparser.Error) as exc:
        return {}, {}, f"plugin .cdmp could not be parsed: {exc}"
    if not read_ok:
        return {}, {}, "plugin .cdmp could not be read"
    core = {key.lower(): value.strip() for key, value in parser.items("Core")} if parser.has_section("Core") else {}
    if not parser.has_section("Codimension"):
        return core, {}, ""
    return core, {key.lower(): value.strip() for key, value in parser.items("Codimension")}, ""


def _safe_int(raw: str, *, label: str) -> tuple[Optional[int], str]:
    text = (raw or "").strip()
    if not text:
        return None, f"{label} is empty"
    try:
        return int(text), ""
    except ValueError:
        return None, f"{label} must be an integer, got {raw!r}"


def _spec_from_manifest(keys: dict[str, str]) -> tuple[Optional[PluginCapabilitySpec], str]:
    """Build capability spec from manifest keys; return ``(spec, error)``."""
    if "minpluginapi" not in keys and "requiredcapabilities" not in keys and "maxpluginapi" not in keys:
        return None, ""
    min_raw = keys.get("minpluginapi", "1")
    min_api, err = _safe_int(min_raw, label="MinPluginAPI")
    if err:
        return None, err
    assert min_api is not None
    max_api: Optional[int] = None
    max_raw = keys.get("maxpluginapi", "").strip()
    if max_raw:
        max_api, err = _safe_int(max_raw, label="MaxPluginAPI")
        if err:
            return None, err
    required_raw = keys.get("requiredcapabilities", "")
    required = frozenset(part.strip() for part in required_raw.split(",") if part.strip())
    try:
        return (
            PluginCapabilitySpec(
                min_api_version=min_api,
                max_api_version=max_api,
                required=required,
            ),
            "",
        )
    except (TypeError, ValueError) as exc:
        return None, f"invalid capability manifest: {exc}"


def _resolve_entrypoint(core_keys: dict[str, str], cdm_keys: dict[str, str]) -> str:
    """Entrypoint from ``[Codimension] Entrypoint`` or ``[Core] Module``."""
    return (cdm_keys.get("entrypoint") or core_keys.get("module") or "").strip()


def build_static_plugin_policy(
    *,
    info_path: str,
    module_filepath: str,
    name: str = "",
    version: str = "0",
    require_manifest: bool | None = None,
    plugin_path: str = "",
) -> StaticPluginPolicy:
    """Combine ``.cdmp`` ``[Codimension]`` keys with optional source heuristics.

    When ``require_manifest`` is true (default for non-bundled paths), the
    Codimension block must be complete; source-based legacy fallbacks are disabled.
    """
    source_path = resolve_plugin_source_path(module_filepath)
    text = _read_text(source_path) if source_path else ""
    path_for_trust = plugin_path or info_path or module_filepath or source_path
    if require_manifest is None:
        require_manifest = not is_trusted_bundled_plugin_path(path_for_trust)

    core_keys, cdm_keys, parse_err = _parse_cdmp_sections(info_path)
    entrypoint = _resolve_entrypoint(core_keys, cdm_keys)

    if require_manifest:
        if parse_err:
            return StaticPluginPolicy(
                name=name or "",
                version=version or "0",
                source_path=source_path,
                info_path=info_path or "",
                entrypoint=entrypoint,
                require_manifest=True,
                manifest_error=parse_err,
            )
        if not cdm_keys:
            return StaticPluginPolicy(
                name=name or "",
                version=version or "0",
                source_path=source_path,
                info_path=info_path or "",
                entrypoint=entrypoint,
                require_manifest=True,
                manifest_error="third-party plugin requires a [Codimension] section in .cdmp",
            )
        # Normalize Module into entrypoint key for the required-set check.
        keys = dict(cdm_keys)
        if "entrypoint" not in keys and entrypoint:
            keys["entrypoint"] = entrypoint
        missing = sorted(k for k in REQUIRED_MANIFEST_KEYS if k not in keys)
        if missing:
            return StaticPluginPolicy(
                name=name or "",
                version=version or "0",
                source_path=source_path,
                info_path=info_path or "",
                entrypoint=entrypoint,
                require_manifest=True,
                manifest_error=("third-party [Codimension] missing keys: " + ", ".join(missing)),
            )
        if not keys.get("entrypoint", "").strip():
            return StaticPluginPolicy(
                name=name or "",
                version=version or "0",
                source_path=source_path,
                info_path=info_path or "",
                entrypoint="",
                require_manifest=True,
                manifest_error="third-party plugin entrypoint/Module is empty",
            )
        category = keys.get("category", "").strip() or None
        if category and category not in KNOWN_CATEGORIES:
            return StaticPluginPolicy(
                name=name or "",
                version=version or "0",
                category=category,
                source_path=source_path,
                info_path=info_path or "",
                entrypoint=keys["entrypoint"],
                require_manifest=True,
                manifest_error=f"unknown plugin category {category!r}",
            )
        min_ide = keys.get("minideversion", "").strip() or None
        if not min_ide:
            return StaticPluginPolicy(
                name=name or "",
                version=version or "0",
                category=category,
                source_path=source_path,
                info_path=info_path or "",
                entrypoint=keys["entrypoint"],
                require_manifest=True,
                manifest_error="MinIDEVersion is empty",
            )
        spec, spec_err = _spec_from_manifest(keys)
        if spec_err:
            return StaticPluginPolicy(
                name=name or "",
                version=version or "0",
                category=category,
                min_ide_version=min_ide,
                source_path=source_path,
                info_path=info_path or "",
                entrypoint=keys["entrypoint"],
                require_manifest=True,
                manifest_error=spec_err,
            )
        if spec is None:
            return StaticPluginPolicy(
                name=name or "",
                version=version or "0",
                category=category,
                min_ide_version=min_ide,
                source_path=source_path,
                info_path=info_path or "",
                entrypoint=keys["entrypoint"],
                require_manifest=True,
                manifest_error="MinPluginAPI / RequiredCapabilities could not be parsed",
            )
        return StaticPluginPolicy(
            name=name or "",
            version=version or "0",
            category=category,
            min_ide_version=min_ide,
            capability_spec=spec,
            source_path=source_path,
            info_path=info_path or "",
            entrypoint=keys["entrypoint"],
            require_manifest=True,
        )

    # Bundled / trusted: allow source heuristics, but never raise on bad ints.
    category = cdm_keys.get("category") or guess_category_from_text(text)
    if category and category not in KNOWN_CATEGORIES:
        category = None

    min_ide = cdm_keys.get("minideversion") or extract_min_ide_version_from_source(text)
    spec, spec_err = _spec_from_manifest(cdm_keys)
    if spec_err:
        return StaticPluginPolicy(
            name=name or "",
            version=version or "0",
            category=category,
            min_ide_version=min_ide,
            source_path=source_path,
            info_path=info_path or "",
            entrypoint=entrypoint,
            require_manifest=False,
            manifest_error=spec_err,
        )
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
        entrypoint=entrypoint,
        require_manifest=False,
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
    if policy.manifest_error:
        err = policy.manifest_error.lower()
        if "minpluginapi" in err or "maxpluginapi" in err or "capability" in err:
            code = incompatible_capabilities
        elif "ide" in err and "version" in err:
            code = incompatible_ide
        else:
            code = bad_base_class
        return StaticPolicyDecision(
            ok=False,
            reason=policy.manifest_error,
            conflict_code=code,
        )

    if policy.require_manifest:
        if not policy.category:
            return StaticPolicyDecision(
                ok=False,
                reason="third-party plugin category missing in [Codimension] (fail-closed)",
                conflict_code=bad_base_class,
            )
        if policy.capability_spec is None:
            return StaticPolicyDecision(
                ok=False,
                reason="third-party plugin capability requirements missing in [Codimension] (fail-closed)",
                conflict_code=incompatible_capabilities,
            )
        if not policy.min_ide_version:
            return StaticPolicyDecision(
                ok=False,
                reason="third-party plugin MinIDEVersion missing in [Codimension] (fail-closed)",
                conflict_code=incompatible_ide,
            )
        if not policy.entrypoint:
            return StaticPolicyDecision(
                ok=False,
                reason="third-party plugin entrypoint missing (fail-closed)",
                conflict_code=bad_base_class,
            )

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
    "REQUIRED_MANIFEST_KEYS",
    "StaticPluginPolicy",
    "StaticPolicyDecision",
    "build_static_plugin_policy",
    "evaluate_static_plugin_policy",
    "extract_capability_spec_from_source",
    "extract_min_ide_version_from_source",
    "guess_category_from_text",
    "is_trusted_bundled_plugin_path",
    "resolve_plugin_source_path",
]
