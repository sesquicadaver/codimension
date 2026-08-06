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

"""Immutable analysis environment snapshot (R110).

Captures the effective Python used for import/analysis, the source kind
matching ``venvbootstrap.describeAnalysisPythonSource``, optional
site-packages roots, and the project id. Construction from a live project
is R111; this module defines the typed value object.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal, Optional, Sequence

# Keep string values identical to ``utils.venvbootstrap`` SOURCE_* constants.
SourceKind = Literal["configured", "session", "auto", "ide", "invalid"]

VALID_SOURCE_KINDS: frozenset[str] = frozenset(
    {
        "configured",
        "session",
        "auto",
        "ide",
        "invalid",
    }
)


def _normalize_site_packages_roots(roots: Optional[Iterable[str]]) -> tuple[str, ...]:
    """Deduplicate and drop empty site-packages paths, preserving order."""
    if not roots:
        return ()
    seen: set[str] = set()
    out: list[str] = []
    for raw in roots:
        path = (raw or "").strip()
        if not path or path in seen:
            continue
        seen.add(path)
        out.append(path)
    return tuple(out)


def resolve_site_packages_roots(python_path: str) -> tuple[str, ...]:
    """Return site-packages roots for ``python_path`` (0 or 1 today)."""
    from .run import getVenvSitePackages

    site = getVenvSitePackages(python_path)
    if site:
        return (site,)
    return ()


@dataclass(frozen=True)
class AnalysisEnvironment:
    """Immutable snapshot of the analysis Python environment.

    Attributes:
        python_path: Interpreter path from describe/resolution (for
            ``invalid``, the configured display path — not a silent IDE
            fallback).
        source_kind: One of ``configured`` / ``session`` / ``auto`` /
            ``ide`` / ``invalid``.
        site_packages_roots: Ordered site-packages directories for import
            resolution (empty for bare IDE / non-venv interpreters).
        project_id: Project UUID when known; ``None`` when no project.
    """

    python_path: str
    source_kind: SourceKind
    site_packages_roots: tuple[str, ...] = ()
    project_id: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate kind and normalize site-packages to a tuple."""
        if self.source_kind not in VALID_SOURCE_KINDS:
            raise ValueError(f"unknown source_kind: {self.source_kind!r}")
        # frozen=True: use object.__setattr__ for normalization
        roots = _normalize_site_packages_roots(self.site_packages_roots)
        if roots != self.site_packages_roots:
            object.__setattr__(self, "site_packages_roots", roots)
        path = self.python_path or ""
        if path != self.python_path:
            object.__setattr__(self, "python_path", path)

    @property
    def is_broken(self) -> bool:
        """True when the configured interpreter is missing/unusable."""
        return self.source_kind == "invalid"

    @property
    def is_ide(self) -> bool:
        """True when analysis falls back to the IDE interpreter."""
        return self.source_kind == "ide"

    @classmethod
    def from_source(
        cls,
        source_kind: str,
        python_path: str,
        *,
        project_id: Optional[str] = None,
        site_packages_roots: Optional[Sequence[str]] = None,
        resolve_site_packages: bool = True,
    ) -> AnalysisEnvironment:
        """Build an environment from describe-style ``(kind, path)`` inputs.

        When ``site_packages_roots`` is omitted and ``resolve_site_packages``
        is True, roots are derived via ``getVenvSitePackages`` (skipped for
        ``invalid`` so a broken path does not invent packages).
        """
        if source_kind not in VALID_SOURCE_KINDS:
            raise ValueError(f"unknown source_kind: {source_kind!r}")
        kind: SourceKind = source_kind  # type: ignore[assignment]
        if site_packages_roots is not None:
            roots = _normalize_site_packages_roots(site_packages_roots)
        elif resolve_site_packages and kind != "invalid":
            roots = resolve_site_packages_roots(python_path)
        else:
            roots = ()
        return cls(
            python_path=python_path,
            source_kind=kind,
            site_packages_roots=roots,
            project_id=project_id,
        )
