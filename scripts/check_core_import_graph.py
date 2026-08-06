#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T085/R100: fail if Qt-free packages import Qt or UI packages.

Covers ``codimension.core``, ``codimension.infrastructure``, and selected
utils modules (R100: ``utils.importutils``).

Static AST gate: Import/ImportFrom (incl. relative) and literal
``importlib.import_module`` / ``__import__`` string arguments.
Non-literal dynamic imports are out of scope (document residual risk).
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_ROOTS = [
    ROOT / "codimension" / "core",
    ROOT / "codimension" / "infrastructure",
]
# R100+: individual utils modules that must stay headless/Qt-free.
QTFREE_UTILS_FILES = [
    ROOT / "codimension" / "utils" / "importutils.py",
]

FORBIDDEN_ROOTS = frozenset(
    {
        "PyQt5",
        "PyQt6",
        "ui",
        "flowui",
        "editor",
        "diagram",
        "cdmplugins",
        "search",
        "debugger",
        "autocomplete",
        "profiling",
        "plugins",
    }
)

FORBIDDEN_UNDER_CODIMENSION = frozenset(
    {
        "ui",
        "flowui",
        "editor",
        "diagram",
        "search",
        "debugger",
        "autocomplete",
        "profiling",
        "plugins",
    }
)


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
        # from ..ui import x  -> module='ui'
        # from .. import ui   -> module=None, names=['ui']
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


def _is_forbidden(imported: str) -> bool:
    """True if ``imported`` is a forbidden Qt/UI dependency."""
    parts = imported.split(".")
    if not parts:
        return False
    if parts[0] in FORBIDDEN_ROOTS:
        return True
    if parts[0] == "codimension" and len(parts) >= 2 and parts[1] in FORBIDDEN_UNDER_CODIMENSION:
        return True
    return False


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
    if not is_import_module:
        return []
    if not node.args:
        return []
    arg0 = node.args[0]
    if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
        return [arg0.value]
    return []


def check_file(path: Path) -> list[str]:
    """Return failure messages for one Python file."""
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    module_name = _module_qualname(path)
    failures: list[str] = []

    def _fail(lineno: int, name: str) -> None:
        try:
            loc = path.relative_to(ROOT)
        except ValueError:
            loc = path
        failures.append(f"{loc}:{lineno}: forbidden import {name!r}")

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for name in _imported_names(node, module_name):
                if _is_forbidden(name):
                    _fail(node.lineno, name)
        for name in _dynamic_import_names(node):
            if _is_forbidden(name):
                _fail(getattr(node, "lineno", 0), name)
    return failures


def main() -> int:
    """Scan Qt-free roots and R100 utils files for forbidden imports."""
    failures: list[str] = []
    for base in CORE_ROOTS:
        if not base.is_dir():
            failures.append(f"missing: {base.relative_to(ROOT)}")
            continue
        for path in sorted(base.rglob("*.py")):
            failures.extend(check_file(path))
    for path in QTFREE_UTILS_FILES:
        if not path.is_file():
            failures.append(f"missing: {path.relative_to(ROOT)}")
            continue
        failures.extend(check_file(path))
    if failures:
        print("T085/R100 import-graph gate FAILED:")
        for item in failures:
            print(f"  {item}")
        return 1
    print("T085/R100 OK: core/infrastructure/importutils have no Qt/UI import edges")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
