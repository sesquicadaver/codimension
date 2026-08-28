#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R103/R195: enforce the named-layer module boundary matrix in CI.

Layers: ``core``, ``infrastructure``, ``app``, ``utils``, ``ui``, ``plugins``,
``mcp_backend`` (R182).

Static AST gate over Import/ImportFrom (incl. relative) and literal
``importlib.import_module`` / ``__import__`` string arguments.

R195 tightens ``utils``: the open ``utils → ui|plugins`` floor is closed.
Only grandfathered modules listed in ``UTILS_LEGACY_EDGES`` may still reach
``ui`` / ``plugins`` / ``qt``. New utils files that import those layers fail.
See ``doc/technology/utils-side-effect-inventory.md``.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODIM = ROOT / "codimension"

NAMED_LAYERS = frozenset(
    {
        "core",
        "infrastructure",
        "app",
        "utils",
        "ui",
        "plugins",
        "mcp_backend",
    }
)

# Importer → set of other named layers it may import.
# Self-imports and non-named packages (parsers, editor, stdlib, …) are ignored.
ALLOWED_EDGES: dict[str, frozenset[str]] = {
    "core": frozenset(),
    "infrastructure": frozenset({"core", "utils"}),
    "app": frozenset({"core", "infrastructure", "utils"}),
    # R195: utils floor excludes ui/plugins; see UTILS_LEGACY_EDGES.
    "utils": frozenset({"core", "infrastructure", "app"}),
    "ui": frozenset({"core", "infrastructure", "app", "utils", "plugins"}),
    "plugins": frozenset({"core", "infrastructure", "app", "utils", "ui"}),
    # R182: MCP process wraps headless core only (no ui/plugins/qt).
    "mcp_backend": frozenset({"core", "infrastructure", "app", "utils"}),
}

# Synthetic layer for Qt bindings — never allowed into Qt-free packages.
QT_LAYER = "qt"
QTFREE_LAYERS = frozenset({"core", "infrastructure", "app", "mcp_backend"})

# R195: grandfathered utils → {ui, plugins, qt} edges (posix path from repo root).
# Shrink this map in R196+ when a hotspot is extracted; do not grow it.
UTILS_LEGACY_EDGES: dict[str, frozenset[str]] = {
    "codimension/utils/colorfont.py": frozenset({"ui"}),
    "codimension/utils/fileutils.py": frozenset({"ui"}),
    "codimension/utils/globals.py": frozenset({"plugins"}),
    "codimension/utils/pixmapcache.py": frozenset({"ui"}),
    "codimension/utils/plantumlcache.py": frozenset({"ui"}),
    "codimension/utils/project.py": frozenset({"ui", QT_LAYER}),
    "codimension/utils/runmanager.py": frozenset({"ui"}),
    "codimension/utils/settings.py": frozenset({"ui"}),
    "codimension/utils/skin.py": frozenset({"ui"}),
    "codimension/utils/ssh_project_runtime.py": frozenset({"ui"}),
    "codimension/utils/watcher.py": frozenset({QT_LAYER}),
    "codimension/utils/webresourcecache.py": frozenset({"ui"}),
}


def _posix_rel(path: Path) -> str:
    """Repo-relative posix path for allowlist keys."""
    return path.resolve().relative_to(ROOT).as_posix()


def _module_qualname(path: Path) -> str:
    """Return dotted module name for a file under the repo root."""
    rel = path.resolve().relative_to(ROOT)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = Path(parts[-1]).stem
    return ".".join(parts)


def _resolve_from(module_name: str, level: int, imported_module: str | None) -> str | None:
    """Resolve ImportFrom target to an absolute dotted name."""
    pkg_parts = module_name.split(".")
    if level > len(pkg_parts):
        return None
    base = pkg_parts[: len(pkg_parts) - level]
    if imported_module:
        return ".".join(base + imported_module.split("."))
    return ".".join(base) if base else None


def _imported_names(node: ast.AST, module_name: str) -> list[str]:
    """Fully-qualified import names referenced by a node."""
    names: list[str] = []
    if isinstance(node, ast.Import):
        for alias in node.names:
            names.append(alias.name)
        return names
    if not isinstance(node, ast.ImportFrom):
        return names
    level = node.level or 0
    if level > 0:
        if node.module:
            resolved = _resolve_from(module_name, level, node.module)
            if resolved:
                if node.names and not any(a.name == "*" for a in node.names):
                    for alias in node.names:
                        names.append(f"{resolved}.{alias.name}")
                else:
                    names.append(resolved)
        else:
            base = _resolve_from(module_name, level, None)
            if base:
                for alias in node.names:
                    if alias.name == "*":
                        names.append(base)
                    else:
                        names.append(f"{base}.{alias.name}")
        return names
    if not node.module:
        return names
    base = node.module
    if node.names and any(a.name == "*" for a in node.names):
        names.append(base)
    else:
        for alias in node.names:
            names.append(f"{base}.{alias.name}")
        if not node.names:
            names.append(base)
    return names


def _dynamic_import_names(node: ast.AST) -> list[str]:
    """Literal module names from importlib.import_module / __import__ calls."""
    if not isinstance(node, ast.Call):
        return []
    func = node.func
    is_import_module = False
    if isinstance(func, ast.Attribute) and func.attr == "import_module":
        is_import_module = True
    elif isinstance(func, ast.Name) and func.id in {"import_module", "__import__"}:
        is_import_module = True
    if not is_import_module or not node.args:
        return []
    arg0 = node.args[0]
    if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
        return [arg0.value]
    return []


def _layer_of_module(imported: str) -> str | None:
    """Map an import name to a named layer or ``qt``; else None."""
    parts = imported.split(".")
    if not parts:
        return None
    if parts[0] in {"PyQt5", "PyQt6"}:
        return QT_LAYER
    if parts[0] == "codimension" and len(parts) >= 2:
        if parts[1] in NAMED_LAYERS:
            return parts[1]
        return None
    if parts[0] in NAMED_LAYERS:
        return parts[0]
    return None


def _importer_layer(path: Path) -> str | None:
    """Named layer owning ``path``, or None."""
    try:
        rel = path.resolve().relative_to(CODIM)
    except ValueError:
        return None
    top = rel.parts[0]
    return top if top in NAMED_LAYERS else None


def _utils_legacy_allows(path: Path, dst: str) -> bool:
    """True if ``path`` is grandfathered for destination layer ``dst``."""
    return dst in UTILS_LEGACY_EDGES.get(_posix_rel(path), frozenset())


def check_file(path: Path) -> list[str]:
    """Return boundary violations for one Python file."""
    importer = _importer_layer(path)
    if importer is None:
        return []
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    module_name = _module_qualname(path)
    allowed = ALLOWED_EDGES[importer]
    failures: list[str] = []

    def _fail(lineno: int, imported: str, dst: str) -> None:
        loc = path.relative_to(ROOT)
        failures.append(f"{loc}:{lineno}: illegal edge {importer} → {dst} (import {imported!r})")

    names: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for name in _imported_names(node, module_name):
                names.append((node.lineno, name))
        for name in _dynamic_import_names(node):
            names.append((getattr(node, "lineno", 0), name))

    for lineno, imported in names:
        dst = _layer_of_module(imported)
        if dst is None or dst == importer:
            continue
        if importer == "utils" and dst in {"ui", "plugins", QT_LAYER}:
            if _utils_legacy_allows(path, dst):
                continue
            _fail(lineno, imported, dst)
            continue
        if dst == QT_LAYER:
            if importer in QTFREE_LAYERS:
                _fail(lineno, imported, dst)
            continue
        if dst not in allowed:
            _fail(lineno, imported, dst)
    return failures


def matrix_as_rows() -> list[tuple[str, str]]:
    """Return sorted (importer, allowed_targets) rows for docs/tests."""
    rows: list[tuple[str, str]] = []
    for importer in sorted(ALLOWED_EDGES):
        targets = ", ".join(sorted(ALLOWED_EDGES[importer])) or "(none)"
        rows.append((importer, targets))
    return rows


def main() -> int:
    """Scan named layers and report illegal boundary edges."""
    failures: list[str] = []
    for layer in sorted(NAMED_LAYERS):
        base = CODIM / layer
        if not base.is_dir():
            failures.append(f"missing layer package: {base.relative_to(ROOT)}")
            continue
        for path in sorted(base.rglob("*.py")):
            failures.extend(check_file(path))
    # Stale allowlist entries must not linger after a file is removed/renamed.
    for rel in sorted(UTILS_LEGACY_EDGES):
        if not (ROOT / rel).is_file():
            failures.append(f"stale UTILS_LEGACY_EDGES entry (missing file): {rel}")
    if failures:
        print("R103/R195 module-boundary gate FAILED:")
        for item in failures:
            print(f"  {item}")
        return 1
    print("R103/R195 OK: named-layer boundary matrix holds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
