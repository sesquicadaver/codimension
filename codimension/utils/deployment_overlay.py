# -*- coding: utf-8 -*-
#
# codimension - deployment overlay hints (R162)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Read-only Dockerfile / Compose detection overlay (R162).

Qt-free scanners + R135 OverlayLayer. Does not parse or mutate deploy
files — only surfaces presence hints for the flow UI.
"""

from __future__ import annotations

import logging
import os
import re
import weakref
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from core.overlay import OverlayContext
from utils.overlay_host import OverlayHost, flow_overlay_host

_LOG = logging.getLogger("codimension.deployment_overlay")

DEPLOYMENT_LAYER_ID = "deployment"

_DOCKERFILE_RE = re.compile(r"^(Dockerfile([.].+)?|.+\.dockerfile)$", re.IGNORECASE)
_COMPOSE_EXACT = frozenset(
    {
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
    }
)
_COMPOSE_RE = re.compile(r"^docker-compose([.].+)?\.(ya?ml)$", re.IGNORECASE)
_SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        "node_modules",
        ".tox",
        ".mypy_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".eggs",
    }
)
_MAX_WALK_FILES = 5_000


@dataclass(frozen=True, slots=True)
class DeploymentHints:
    """Detected deployment artifacts under a project root."""

    root: str
    dockerfiles: tuple[str, ...]
    compose_files: tuple[str, ...]

    @property
    def has_docker(self) -> bool:
        """True when at least one Dockerfile-like file was found."""
        return bool(self.dockerfiles)

    @property
    def has_compose(self) -> bool:
        """True when at least one Compose file was found."""
        return bool(self.compose_files)

    @property
    def has_any(self) -> bool:
        """True when any deployment artifact was found."""
        return self.has_docker or self.has_compose


@dataclass(frozen=True, slots=True)
class DeploymentBadgeInfo:
    """Compact badges for the flow navigation bar."""

    docker_badge: str
    compose_badge: str
    tooltip: str
    hints: DeploymentHints


def is_dockerfile_name(name: str) -> bool:
    """Return True when ``name`` looks like a Dockerfile."""
    return bool(_DOCKERFILE_RE.match(os.path.basename(name)))


def is_compose_name(name: str) -> bool:
    """Return True when ``name`` looks like a Compose file."""
    base = os.path.basename(name)
    lowered = base.lower()
    if lowered in _COMPOSE_EXACT:
        return True
    return bool(_COMPOSE_RE.match(base))


def classify_deployment_path(path: str) -> Optional[str]:
    """Return ``\"dockerfile\"``, ``\"compose\"``, or ``None`` for ``path``."""
    name = os.path.basename(path)
    if is_dockerfile_name(name):
        return "dockerfile"
    if is_compose_name(name):
        return "compose"
    return None


def detect_deployment_artifacts(
    root: str,
    *,
    paths: Optional[Sequence[str]] = None,
    max_files: int = _MAX_WALK_FILES,
) -> DeploymentHints:
    """Detect Dockerfile / Compose files under ``root`` (read-only).

    When ``paths`` is provided, only those absolute/relative paths are
    classified (ideal for ``project.filesList``). Otherwise a shallow
    directory walk is used (skipping common VCS/venv dirs).
    """
    abs_root = os.path.abspath(root) if root else ""
    dockerfiles: list[str] = []
    compose_files: list[str] = []

    def _add(path: str) -> None:
        kind = classify_deployment_path(path)
        if kind == "dockerfile":
            dockerfiles.append(path)
        elif kind == "compose":
            compose_files.append(path)

    if paths is not None:
        for raw in paths:
            if not raw:
                continue
            path = raw if os.path.isabs(raw) else os.path.join(abs_root, raw)
            if os.path.isfile(path):
                _add(os.path.abspath(path))
    elif abs_root and os.path.isdir(abs_root):
        seen = 0
        for dirpath, dirnames, filenames in os.walk(abs_root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIR_NAMES and not d.startswith(".")]
            for name in filenames:
                seen += 1
                if seen > max_files:
                    break
                _add(os.path.join(dirpath, name))
            if seen > max_files:
                break

    dockerfiles_t = tuple(sorted(set(dockerfiles)))
    compose_t = tuple(sorted(set(compose_files)))
    return DeploymentHints(root=abs_root, dockerfiles=dockerfiles_t, compose_files=compose_t)


def format_deployment_badge(hints: DeploymentHints) -> DeploymentBadgeInfo:
    """Build nav-bar badges and a tooltip from ``hints``."""
    docker_badge = f"deploy:docker×{len(hints.dockerfiles)}" if hints.dockerfiles else "deploy:—"
    compose_badge = f"compose:{len(hints.compose_files)}" if hints.compose_files else ""
    lines = ["Deployment artifacts (read-only detection)"]
    if hints.dockerfiles:
        lines.append("Dockerfiles:")
        lines.extend(f"  {p}" for p in hints.dockerfiles)
    if hints.compose_files:
        lines.append("Compose:")
        lines.extend(f"  {p}" for p in hints.compose_files)
    if not hints.has_any:
        lines.append("No Dockerfile or Compose file found.")
    return DeploymentBadgeInfo(
        docker_badge=docker_badge,
        compose_badge=compose_badge,
        tooltip="\n".join(lines),
        hints=hints,
    )


def empty_deployment_badge(root: str = "") -> DeploymentBadgeInfo:
    """Badge payload when nothing is detected."""
    return format_deployment_badge(DeploymentHints(root=root, dockerfiles=(), compose_files=()))


def detect_for_project(project) -> DeploymentHints:
    """Detect artifacts for a loaded project (filesList when available)."""
    if project is None or not getattr(project, "isLoaded", lambda: False)():
        return DeploymentHints(root="", dockerfiles=(), compose_files=())
    root = ""
    if hasattr(project, "getProjectDir"):
        raw = project.getProjectDir()
        if raw:
            root = str(raw)
    paths: Optional[list[str]] = None
    try:
        files_list = getattr(project, "filesList", None)
        if files_list:
            paths = [p for p in files_list if isinstance(p, str)]
    except Exception:
        _LOG.debug("deployment overlay: filesList unavailable", exc_info=True)
        paths = None
    hints = detect_deployment_artifacts(root, paths=paths)
    # Project file lists often omit non-Python artifacts; fall back to a walk.
    if not hints.has_any and root:
        hints = detect_deployment_artifacts(root, paths=None)
    return hints


class DeploymentOverlayLayer:
    """R135 overlay that refreshes Dockerfile / Compose presence badges."""

    layer_id = DEPLOYMENT_LAYER_ID

    def __init__(self) -> None:
        self.last_badge: Optional[DeploymentBadgeInfo] = None
        self.last_hints: Optional[DeploymentHints] = None
        self._weak_sinks: list[weakref.WeakMethod] = []
        self._strong_sinks: list[Callable[[DeploymentBadgeInfo], None]] = []

    def add_sink(self, callback: Callable[[DeploymentBadgeInfo], None]) -> None:
        """Register a UI callback; bound methods are held weakly."""
        try:
            self._weak_sinks.append(weakref.WeakMethod(callback))  # type: ignore[arg-type]
        except TypeError:
            self._strong_sinks.append(callback)

    def on_update(self, context: OverlayContext) -> None:
        """Refresh deployment hints (project-global; path unused)."""
        del context
        self.refresh()

    def refresh(self, project=None) -> DeploymentBadgeInfo:
        """Recompute hints and notify sinks."""
        if project is None:
            try:
                from utils.globals import GlobalData

                project = GlobalData().project
            except Exception:
                _LOG.debug("deployment overlay: GlobalData unavailable", exc_info=True)
                project = None
        try:
            hints = detect_for_project(project)
            badge = format_deployment_badge(hints)
        except Exception:
            _LOG.debug("deployment overlay: refresh failed", exc_info=True)
            badge = empty_deployment_badge()
        self.last_hints = badge.hints
        self.last_badge = badge
        self._notify(badge)
        return badge

    def _notify(self, badge: DeploymentBadgeInfo) -> None:
        alive: list[weakref.WeakMethod] = []
        for ref in self._weak_sinks:
            cb = ref()
            if cb is None:
                continue
            alive.append(ref)
            try:
                cb(badge)
            except Exception:
                _LOG.debug("deployment overlay sink failed", exc_info=True)
        self._weak_sinks = alive
        for cb in list(self._strong_sinks):
            try:
                cb(badge)
            except Exception:
                _LOG.debug("deployment overlay sink failed", exc_info=True)


def ensure_deployment_overlay(host: Optional[OverlayHost] = None) -> DeploymentOverlayLayer:
    """Register the deployment overlay on the flow host if missing."""
    target = host if host is not None else flow_overlay_host()
    if target.registry.has(DEPLOYMENT_LAYER_ID):
        layer = target.registry.get(DEPLOYMENT_LAYER_ID)
        assert isinstance(layer, DeploymentOverlayLayer)
        return layer
    layer = DeploymentOverlayLayer()
    target.register(layer)
    return layer


def relative_hint_paths(hints: DeploymentHints) -> tuple[str, ...]:
    """Return dockerfile + compose paths relative to ``hints.root`` when possible."""
    out: list[str] = []
    root = hints.root or ""
    for path in (*hints.dockerfiles, *hints.compose_files):
        if root and path.startswith(root + os.sep):
            out.append(os.path.relpath(path, root))
        else:
            out.append(path)
    return tuple(out)


__all__ = [
    "DEPLOYMENT_LAYER_ID",
    "DeploymentBadgeInfo",
    "DeploymentHints",
    "DeploymentOverlayLayer",
    "classify_deployment_path",
    "detect_deployment_artifacts",
    "detect_for_project",
    "empty_deployment_badge",
    "ensure_deployment_overlay",
    "format_deployment_badge",
    "is_compose_name",
    "is_dockerfile_name",
    "relative_hint_paths",
]
