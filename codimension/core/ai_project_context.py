# -*- coding: utf-8 -*-
#
# codimension - project-scoped context for AI module analysis (Qt-free)
# Copyright (C) 2026  Codimension Team
# The license is described in the LICENSE file at the root directory.
#

"""Build project-local context so module analysis stays inside the project.

Resolves ``import`` / ``from … import`` targets to files under the project
tree and collects short neighbour excerpts. Stdlib / third-party imports are
listed by name only (no invented APIs).
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from typing import Iterable, Sequence

MAX_NEIGHBOUR_FILES = 8
MAX_NEIGHBOUR_CHARS = 2500
MAX_API_NAMES = 40


@dataclass(frozen=True)
class ProjectModuleContext:
    """Project-scoped facts for one module under analysis."""

    project_dir: str
    module_path: str
    module_relpath: str
    project_py_count: int
    local_imports: tuple[str, ...]
    external_imports: tuple[str, ...]
    neighbour_paths: tuple[str, ...]
    neighbour_excerpts: tuple[tuple[str, str], ...]  # (relpath, excerpt)

    def to_prompt_block(self) -> str:
        """Markdown block injected into the module-analysis user prompt."""
        lines = [
            "## Project context (authoritative)",
            f"Project root: {self.project_dir}",
            f"Module (relative): {self.module_relpath}",
            f"Python modules in project: {self.project_py_count}",
            "",
            "Analyze this module ONLY in the context of this project.",
            "Do not invent project modules, symbols, or call graphs that are not "
            "evidenced below. External packages are out of project scope except "
            "as named dependencies.",
            "",
        ]
        if self.local_imports:
            lines.append("Local (project) imports:")
            lines.extend(f"- {name}" for name in self.local_imports)
            lines.append("")
        if self.external_imports:
            lines.append("External imports (names only):")
            lines.extend(f"- {name}" for name in self.external_imports)
            lines.append("")
        if self.neighbour_excerpts:
            lines.append("Related project modules (excerpts):")
            for rel, excerpt in self.neighbour_excerpts:
                lines.append(f"### {rel}")
                lines.append(excerpt)
                lines.append("")
        elif self.neighbour_paths:
            lines.append("Related project modules (paths only):")
            lines.extend(f"- {p}" for p in self.neighbour_paths)
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"


def extract_import_modules(source: str) -> tuple[str, ...]:
    """Return dotted module names referenced by import statements."""
    try:
        tree = ast.parse(source or "")
    except SyntaxError:
        return ()
    names: list[str] = []
    seen: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = (alias.name or "").strip()
                if mod and mod not in seen:
                    seen.add(mod)
                    names.append(mod)
        elif isinstance(node, ast.ImportFrom):
            if node.level and not node.module:
                # relative import of package itself — skip bare dots
                continue
            mod = (node.module or "").strip()
            if node.level:
                # keep absolute-looking name; resolver uses file location
                mod = ("." * node.level) + mod
            if mod and mod not in seen:
                seen.add(mod)
                names.append(mod)
    return tuple(names)


def _module_candidates(project_dir: str, dotted: str) -> list[str]:
    """Possible filesystem paths for a dotted import under ``project_dir``."""
    dotted = dotted.lstrip(".")
    if not dotted:
        return []
    parts = dotted.split(".")
    base = os.path.join(project_dir, *parts)
    return [
        base + ".py",
        os.path.join(base, "__init__.py"),
    ]


def resolve_import_to_project_file(
    dotted: str,
    *,
    module_path: str,
    project_dir: str,
    project_files: Sequence[str],
) -> str | None:
    """Resolve ``dotted`` to an absolute path in ``project_files``, if any."""
    project_dir = os.path.abspath(project_dir)
    files_set = {os.path.abspath(p) for p in project_files}

    # Relative imports: resolve against the module's package directory.
    if dotted.startswith("."):
        level = len(dotted) - len(dotted.lstrip("."))
        rest = dotted.lstrip(".")
        start = os.path.dirname(os.path.abspath(module_path))
        for _ in range(max(level - 1, 0)):
            start = os.path.dirname(start)
        if rest:
            candidates = _module_candidates(start, rest)
        else:
            candidates = [os.path.join(start, "__init__.py"), start + ".py"]
    else:
        candidates = _module_candidates(project_dir, dotted)
        # Also try resolving from the module's directory (same-package style).
        pkg = os.path.dirname(os.path.abspath(module_path))
        candidates.extend(_module_candidates(pkg, dotted))

    for cand in candidates:
        abs_cand = os.path.abspath(cand)
        if abs_cand in files_set and os.path.isfile(abs_cand):
            return abs_cand
    return None


def _public_api_sketch(source: str, limit: int = MAX_API_NAMES) -> str:
    """One-line sketch of top-level defs/classes for a neighbour module."""
    try:
        tree = ast.parse(source or "")
    except SyntaxError:
        return "(unparseable)"
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name.startswith("_"):
                continue
            kind = "class" if isinstance(node, ast.ClassDef) else "def"
            names.append(f"{kind} {node.name}")
            if len(names) >= limit:
                break
    return ", ".join(names) if names else "(no public top-level defs)"


def build_project_module_context(
    *,
    module_path: str,
    source: str,
    project_dir: str,
    project_files: Sequence[str],
) -> ProjectModuleContext:
    """Assemble project-scoped context for ``module_path``."""
    project_dir = os.path.abspath(project_dir)
    module_path = os.path.abspath(module_path) if module_path else module_path
    rel = os.path.relpath(module_path, project_dir) if module_path else "<buffer>"

    imports = extract_import_modules(source)
    local: list[str] = []
    external: list[str] = []
    neighbours: list[str] = []
    for name in imports:
        resolved = resolve_import_to_project_file(
            name,
            module_path=module_path or project_dir,
            project_dir=project_dir,
            project_files=project_files,
        )
        if resolved:
            display = name.lstrip(".") or name
            local.append(f"{display} → {os.path.relpath(resolved, project_dir)}")
            if resolved not in neighbours and resolved != module_path:
                neighbours.append(resolved)
        else:
            external.append(name.lstrip(".") or name)

    excerpts: list[tuple[str, str]] = []
    for path in neighbours[:MAX_NEIGHBOUR_FILES]:
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                raw = handle.read()
        except OSError:
            continue
        rel_n = os.path.relpath(path, project_dir)
        api = _public_api_sketch(raw)
        body = raw if len(raw) <= MAX_NEIGHBOUR_CHARS else raw[: MAX_NEIGHBOUR_CHARS - 20] + "\n...[truncated]...\n"
        excerpts.append((rel_n, f"Public API: {api}\n\n{body}"))

    return ProjectModuleContext(
        project_dir=project_dir,
        module_path=module_path or "",
        module_relpath=rel,
        project_py_count=len(project_files),
        local_imports=tuple(local),
        external_imports=tuple(external),
        neighbour_paths=tuple(os.path.relpath(p, project_dir) for p in neighbours),
        neighbour_excerpts=tuple(excerpts),
    )


def assert_path_in_project(path: str, project_dir: str, project_files: Iterable[str]) -> str:
    """Return absolute path if it belongs to the project file set.

    Raises:
        ValueError: when the path is outside the project.
    """
    project_dir = os.path.abspath(project_dir)
    if not path or path in {"<buffer>", "<memory>"}:
        raise ValueError(
            "Module is outside the open project (unsaved buffer). Save a project file to run module analysis."
        )
    abs_path = os.path.abspath(path if os.path.isabs(path) else os.path.join(project_dir, path))
    files = {os.path.abspath(p) for p in project_files}
    if abs_path not in files:
        raise ValueError(
            f"Module is outside the open project (not in project .py set): {abs_path}. "
            "Open a project file to run module analysis."
        )
    return abs_path


__all__ = [
    "ProjectModuleContext",
    "assert_path_in_project",
    "build_project_module_context",
    "extract_import_modules",
    "resolve_import_to_project_file",
]
