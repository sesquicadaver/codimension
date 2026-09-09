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

R232 / audit P1-01: re-validate manifest + file identity immediately before
every import (including enable / ``materializePlugin``), so a deferred
candidate cannot bypass policy after on-disk mutation.

R251 / R254: package identity digests all importable ``.py`` members under
bounded per-file / walk budgets. Unreadable or oversized members yield
``PluginFileIdentity.valid is False`` (never a stable empty digest).
"""

from __future__ import annotations

import ast
import configparser
import hashlib
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


@dataclass(frozen=True)
class PluginFileIdentity:
    """On-disk identity of a plugin candidate's ``.cdmp`` + package sources.

    Captured at collection / deferral time and compared again immediately before
    import so enable-after-disable cannot load mutated or swapped files.

    R251: ``package_sha256`` covers all ``.py`` files under the plugin package
    root (not only the entry ``__init__.py`` / module), and digests are computed
    from a single fd with a byte cap (no unbounded ``read()``).

    R254: ``valid`` is explicit — oversized / unreadable members or walk-budget
    violations never produce a stable empty digest that would compare equal.
    """

    info_path: str
    source_path: str
    info_mtime_ns: int
    info_size: int
    info_sha256: str
    source_mtime_ns: int
    source_size: int
    source_sha256: str
    package_sha256: str = ""
    valid: bool = True
    invalid_reason: str = ""


#: Soft cap per plugin file hashed into identity / text parse (R251 / R254).
_MAX_PLUGIN_FILE_BYTES = 2_000_000
#: Walk budgets for package identity (R254).
_MAX_PLUGIN_PACKAGE_FILES = 256
_MAX_PLUGIN_PACKAGE_ENTRIES = 2_048
_MAX_PLUGIN_PACKAGE_DEPTH = 8
_MAX_PLUGIN_PACKAGE_TOTAL_BYTES = 8_000_000


class _PluginIdentityError(Exception):
    """Internal: identity capture failed fail-closed (R254)."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _file_digest_and_stat(path: str) -> tuple[str, int, int]:
    """Return ``(sha256_hex, mtime_ns, size)`` for ``path``.

    Uses one ``open`` + ``fstat`` and a bounded chunked digest (R251).
    Oversized or unreadable files raise :class:`_PluginIdentityError` (R254).
    """
    if not path or not os.path.isfile(path):
        raise _PluginIdentityError(f"plugin file missing or not a regular file: {path!r}")
    try:
        with open(path, "rb") as handle:
            st = os.fstat(handle.fileno())
            size = int(st.st_size)
            if size > _MAX_PLUGIN_FILE_BYTES:
                raise _PluginIdentityError(f"plugin file exceeds {_MAX_PLUGIN_FILE_BYTES} bytes: {path!r}")
            hasher = hashlib.sha256()
            remaining = size if size > 0 else _MAX_PLUGIN_FILE_BYTES
            while remaining > 0:
                chunk = handle.read(min(65_536, remaining))
                if not chunk:
                    break
                hasher.update(chunk)
                remaining -= len(chunk)
            # Trailing bytes beyond stated size (TOCTOU grow) → fail closed.
            if handle.read(1):
                raise _PluginIdentityError(f"plugin file grew during hash: {path!r}")
            mtime_ns = int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000)))
            return hasher.hexdigest(), mtime_ns, size
    except OSError as exc:
        raise _PluginIdentityError(f"plugin file unreadable: {path!r} ({exc})") from exc


def _plugin_package_root(source_path: str) -> str:
    """Directory whose ``.py`` siblings belong to the plugin package identity."""
    if not source_path:
        return ""
    real = os.path.realpath(source_path)
    base = os.path.basename(real)
    if base == "__init__.py":
        return os.path.dirname(real)
    # Single-module plugin: only the entry file (package digest empty / file-only).
    return ""


def _package_py_digest(source_path: str) -> str:
    """Sorted merkle of ``relpath=sha256`` for every ``.py`` under the package root.

    Enforces entry / file / depth / total-byte budgets (R254). Empty package
    directory yields ``""`` only when no ``.py`` members exist (still ``valid``).
    """
    root = _plugin_package_root(source_path)
    if not root or not os.path.isdir(root):
        return ""
    rows: list[str] = []
    entries_seen = 0
    files_seen = 0
    total_bytes = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        rel_dir = os.path.relpath(dirpath, root)
        depth = 0 if rel_dir == os.curdir else rel_dir.count(os.sep) + 1
        if depth > _MAX_PLUGIN_PACKAGE_DEPTH:
            raise _PluginIdentityError(f"plugin package depth exceeds {_MAX_PLUGIN_PACKAGE_DEPTH}: {root!r}")
        dirnames[:] = sorted(d for d in dirnames if d not in {".git", "__pycache__", ".venv", "venv"})
        entries_seen += len(dirnames) + len(filenames)
        if entries_seen > _MAX_PLUGIN_PACKAGE_ENTRIES:
            raise _PluginIdentityError(f"plugin package entry count exceeds {_MAX_PLUGIN_PACKAGE_ENTRIES}: {root!r}")
        for name in sorted(filenames):
            if not name.endswith(".py"):
                continue
            full = os.path.join(dirpath, name)
            if os.path.islink(full):
                raise _PluginIdentityError(f"plugin package rejects symlinked .py: {full!r}")
            files_seen += 1
            if files_seen > _MAX_PLUGIN_PACKAGE_FILES:
                raise _PluginIdentityError(f"plugin package .py count exceeds {_MAX_PLUGIN_PACKAGE_FILES}: {root!r}")
            digest, _, size = _file_digest_and_stat(full)
            total_bytes += size
            if total_bytes > _MAX_PLUGIN_PACKAGE_TOTAL_BYTES:
                raise _PluginIdentityError(
                    f"plugin package total bytes exceed {_MAX_PLUGIN_PACKAGE_TOTAL_BYTES}: {root!r}"
                )
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            rows.append(f"{rel}={digest}")
    if not rows:
        return ""
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def _invalid_plugin_identity(
    *,
    info_path: str,
    source_path: str,
    reason: str,
) -> PluginFileIdentity:
    """Build an explicit invalid identity snapshot (R254)."""
    return PluginFileIdentity(
        info_path=info_path,
        source_path=source_path,
        info_mtime_ns=0,
        info_size=0,
        info_sha256="",
        source_mtime_ns=0,
        source_size=0,
        source_sha256="",
        package_sha256="",
        valid=False,
        invalid_reason=reason,
    )


def capture_plugin_file_identity(
    *,
    info_path: str,
    module_filepath: str,
) -> PluginFileIdentity:
    """Snapshot ``.cdmp`` + entry + package ``.py`` digests for a candidate.

    Always returns a :class:`PluginFileIdentity`. On any member/budget failure
    ``valid`` is ``False`` and digests are empty (R254 fail-closed).
    """
    source_path = resolve_plugin_source_path(module_filepath)
    info_real = os.path.realpath(info_path) if info_path and os.path.isfile(info_path) else (info_path or "")
    source_real = os.path.realpath(source_path) if source_path else ""
    try:
        if not info_path:
            raise _PluginIdentityError("plugin .cdmp path is empty")
        if module_filepath and not source_path:
            raise _PluginIdentityError(f"plugin source could not be resolved from {module_filepath!r}")
        info_sha, info_mtime, info_size = _file_digest_and_stat(info_path)
        src_sha, src_mtime, src_size = _file_digest_and_stat(source_path)
        package_sha = _package_py_digest(source_path)
    except _PluginIdentityError as exc:
        return _invalid_plugin_identity(
            info_path=info_real,
            source_path=source_real,
            reason=exc.reason,
        )
    return PluginFileIdentity(
        info_path=info_real,
        source_path=source_real,
        info_mtime_ns=info_mtime,
        info_size=info_size,
        info_sha256=info_sha,
        source_mtime_ns=src_mtime,
        source_size=src_size,
        source_sha256=src_sha,
        package_sha256=package_sha,
        valid=True,
        invalid_reason="",
    )


def validate_candidate_before_import(
    *,
    info_path: str,
    module_filepath: str,
    name: str = "",
    version: str = "0",
    plugin_path: str = "",
    expected_identity: PluginFileIdentity | None = None,
    ide_version: str,
    require_manifest: bool | None = None,
    bad_base_class: int = 4,
    incompatible_ide: int = 2,
    incompatible_capabilities: int = 8,
) -> StaticPolicyDecision:
    """Fail-closed gate: file identity (optional) + static policy before import.

    Must run immediately before every ``loadPlugins()`` call, including the
    enable path that materializes a previously deferred candidate.
    """
    current = capture_plugin_file_identity(
        info_path=info_path,
        module_filepath=module_filepath,
    )
    if not current.valid:
        return StaticPolicyDecision(
            ok=False,
            reason=(
                "plugin identity invalid "
                f"(info={info_path!r}, source={current.source_path!r}): "
                f"{current.invalid_reason or 'unreadable or oversized member'} (R254)"
            ),
            conflict_code=bad_base_class,
        )
    if expected_identity is not None:
        if not expected_identity.valid:
            return StaticPolicyDecision(
                ok=False,
                reason=("stored plugin identity was invalid at collection; re-enable denied (R254)"),
                conflict_code=bad_base_class,
            )
        if current != expected_identity:
            return StaticPolicyDecision(
                ok=False,
                reason=(
                    "plugin files changed since collection "
                    f"(info={info_path!r}, source={current.source_path!r}); "
                    "re-enable denied (R232)"
                ),
                conflict_code=bad_base_class,
            )
    if require_manifest is None:
        require_manifest = not is_trusted_bundled_plugin_path(plugin_path or info_path or module_filepath)
    policy = build_static_plugin_policy(
        info_path=info_path,
        module_filepath=module_filepath,
        name=name,
        version=version,
        plugin_path=plugin_path,
        require_manifest=require_manifest,
    )
    return evaluate_static_plugin_policy(
        policy,
        ide_version=ide_version,
        bad_base_class=bad_base_class,
        incompatible_ide=incompatible_ide,
        incompatible_capabilities=incompatible_capabilities,
    )


def _read_text(path: str, *, max_bytes: int | None = None) -> str:
    """Read UTF-8 text up to ``max_bytes``; oversized / unreadable → ``\"\"`` (R254)."""
    limit = _MAX_PLUGIN_FILE_BYTES if max_bytes is None else max_bytes
    if not path or not os.path.isfile(path):
        return ""
    try:
        with open(path, "rb") as handle:
            raw = handle.read(limit + 1)
    except OSError:
        return ""
    if len(raw) > limit:
        return ""
    return raw.decode("utf-8", errors="replace")


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


def cdmplugins_package_roots() -> list[str]:
    """Real filesystem roots for the installed ``cdmplugins`` package.

    Tolerates namespace packages and test stubs that omit ``__file__`` but
    still expose ``__path__`` (full-suite pollution must not raise).
    """
    try:
        import cdmplugins
    except Exception:
        return []
    roots: list[str] = []
    file_attr = getattr(cdmplugins, "__file__", None)
    if file_attr:
        roots.append(os.path.realpath(os.path.dirname(os.path.abspath(str(file_attr)))))
    for entry in getattr(cdmplugins, "__path__", None) or []:
        if not entry:
            continue
        roots.append(os.path.realpath(os.path.abspath(str(entry))))
    # Preserve order, drop duplicates.
    unique: list[str] = []
    seen: set[str] = set()
    for root in roots:
        if root in seen:
            continue
        seen.add(root)
        unique.append(root)
    return unique


def is_trusted_bundled_plugin_path(path: str) -> bool:
    """True when ``path`` lives under the shipped ``cdmplugins`` package tree."""
    text = (path or "").strip()
    if not text:
        return False
    real = os.path.realpath(os.path.expanduser(text))
    for root in cdmplugins_package_roots():
        root_sep = root if root.endswith(os.sep) else root + os.sep
        if real == root or real.startswith(root_sep):
            return True
    return False


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
    Content is size-capped before ``ConfigParser`` (R254).
    """
    if not info_path or not os.path.isfile(info_path):
        return {}, {}, "plugin .cdmp info file is missing"
    text = _read_text(info_path)
    if not text:
        # Distinguish empty vs oversized/unreadable via a second size probe.
        try:
            size = os.path.getsize(info_path)
        except OSError:
            size = -1
        if size > _MAX_PLUGIN_FILE_BYTES:
            return {}, {}, f"plugin .cdmp exceeds {_MAX_PLUGIN_FILE_BYTES} bytes"
        if size == 0:
            return {}, {}, "plugin .cdmp is empty"
        return {}, {}, "plugin .cdmp could not be read"
    parser = configparser.ConfigParser()
    try:
        parser.read_string(text)
    except configparser.Error as exc:
        return {}, {}, f"plugin .cdmp could not be parsed: {exc}"
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
    "PluginFileIdentity",
    "StaticPluginPolicy",
    "StaticPolicyDecision",
    "build_static_plugin_policy",
    "capture_plugin_file_identity",
    "cdmplugins_package_roots",
    "evaluate_static_plugin_policy",
    "extract_capability_spec_from_source",
    "extract_min_ide_version_from_source",
    "guess_category_from_text",
    "is_trusted_bundled_plugin_path",
    "resolve_plugin_source_path",
    "validate_candidate_before_import",
]
