# -*- coding: utf-8 -*-
#
# codimension - graphics python two-way code editor and analyzer
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""DependencyManifest — formal install sources for a project (R120).

Builds on the same discovery as ``venvbootstrap.collectInstallSources``:
requirement files, ``pyproject.toml``, and unresolved third-party imports.
Provides a lock/install hint and export to ``requirements.txt``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Sequence


@dataclass(frozen=True)
class DependencyManifest:
    """Immutable snapshot of project dependency install sources.

    Attributes:
        requirement_files: Absolute paths to ``requirements*.txt`` under the
            project root (sorted).
        has_pyproject: True when ``pyproject.toml`` exists at the project root.
        unresolved_packages: Sorted unique top-level package names inferred
            from unresolved imports.
        project_dir: Absolute project directory when known.
        project_id: Project UUID when known.
    """

    requirement_files: tuple[str, ...] = ()
    has_pyproject: bool = False
    unresolved_packages: tuple[str, ...] = ()
    project_dir: Optional[str] = None
    project_id: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        """Legacy dict shape used by ``collectInstallSources`` / VENV wizard."""
        return {
            "requirement_files": list(self.requirement_files),
            "has_pyproject": self.has_pyproject,
            "unresolved_packages": list(self.unresolved_packages),
        }

    def requirements_lines(self) -> list[str]:
        """Exportable requirements body (one package name per line)."""
        return list(self.unresolved_packages)

    def lock_hint(self) -> str:
        """Short pip-oriented install hint (empty when nothing to install).

        Preference: existing requirements file → editable pyproject → bare
        unresolved package list.
        """
        req = self._preferred_requirements_file()
        if req:
            return f"pip install -r {req}"
        if self.has_pyproject and self.project_dir:
            return f"pip install -e {self.project_dir}"
        if self.has_pyproject:
            return "pip install -e ."
        if self.unresolved_packages:
            return "pip install " + " ".join(self.unresolved_packages)
        return ""

    def write_requirements(self, path: str, *, mode: str = "w") -> int:
        """Write unresolved packages to ``path`` (see ``writeRequirementsFile``)."""
        from .importutils import writeRequirementsFile

        written: int = writeRequirementsFile(path, self.unresolved_packages, mode)
        return written

    def _preferred_requirements_file(self) -> Optional[str]:
        """Prefer ``requirements.txt``, else the first discovered file."""
        if not self.requirement_files:
            return None
        for path in self.requirement_files:
            if os.path.basename(path) == "requirements.txt":
                return path
        return self.requirement_files[0]


def _scan_requirement_files(project_dir: str) -> tuple[str, ...]:
    """Return sorted absolute ``requirements*.txt`` paths under ``project_dir``."""
    if not project_dir or not os.path.isdir(project_dir):
        return ()
    found: list[str] = []
    for path in sorted(Path(project_dir).glob("requirements*.txt")):
        if path.is_file():
            found.append(str(path.resolve()))
    return tuple(found)


def _has_pyproject(project_dir: Optional[str]) -> bool:
    """True when ``pyproject.toml`` exists in ``project_dir``."""
    if not project_dir:
        return False
    return os.path.isfile(os.path.join(project_dir, "pyproject.toml"))


def buildDependencyManifest(
    project,
    *,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    unresolved_packages: Optional[Sequence[str]] = None,
) -> DependencyManifest:
    """Build a ``DependencyManifest`` from a loaded project (R120).

    When ``unresolved_packages`` is omitted, scans ``project.filesList`` via
    ``generateRequirementsFromProject``. Pass an explicit sequence in tests
    to avoid GlobalData / parser coupling.
    """
    project_dir = None
    project_id = None
    files: Iterable[str] = ()
    if project is not None:
        get_dir = getattr(project, "getProjectDir", None)
        if callable(get_dir):
            project_dir = get_dir() or None
        props = getattr(project, "props", None) or {}
        project_id = props.get("uuid") or None
        files = getattr(project, "filesList", None) or ()

    req_files = _scan_requirement_files(project_dir or "")
    has_pp = _has_pyproject(project_dir)

    if unresolved_packages is not None:
        packages = tuple(sorted({p for p in unresolved_packages if p}))
    else:
        packages = ()
        try:
            from .importutils import generateRequirementsFromProject

            packages_set, _ = generateRequirementsFromProject(files, progress_callback)
            packages = tuple(sorted(packages_set))
        except Exception:
            packages = ()

    return DependencyManifest(
        requirement_files=req_files,
        has_pyproject=has_pp,
        unresolved_packages=packages,
        project_dir=os.path.abspath(project_dir) if project_dir else None,
        project_id=project_id,
    )


def buildDependencyManifestFromDir(
    project_dir: str,
    *,
    files: Optional[Sequence[str]] = None,
    unresolved_packages: Optional[Sequence[str]] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> DependencyManifest:
    """Headless builder from a project directory (no ``.cdm3`` required).

    When ``files`` is omitted, walks ``*.py`` under ``project_dir`` (non-recursive
    root only is insufficient for real projects — use a shallow walk excluding
    common venv dirs).
    """
    root = os.path.abspath(project_dir)
    if files is None and unresolved_packages is None:
        files = tuple(_iter_project_python_files(root))

    class _DirProject:
        def getProjectDir(self) -> str:
            return root + os.sep

        @property
        def props(self) -> dict:
            return {}

        @property
        def filesList(self):
            return files or ()

    return buildDependencyManifest(
        _DirProject(),
        progress_callback=progress_callback,
        unresolved_packages=unresolved_packages,
    )


def _iter_project_python_files(root: str) -> list[str]:
    """Collect ``.py`` files under ``root``, skipping venv/cache trees."""
    skip_dirs = {
        ".venv",
        "venv",
        "env",
        ".git",
        "__pycache__",
        ".mypy_cache",
        ".tox",
        "node_modules",
        ".eggs",
        "dist",
        "build",
    }
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.endswith(".egg-info")]
        for name in filenames:
            if name.endswith(".py"):
                out.append(os.path.join(dirpath, name))
    return out
