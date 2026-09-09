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

"""ApplicationServices — project create/load/switch/unload façade (R101 / R236 / R257)."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable, Mapping, Optional, Protocol


class ProjectPort(Protocol):
    """Minimal project surface used by the application façade.

    Matches ``CodimensionProject`` method names so the real project object can
    be injected without adapters (R102 / R236).
    """

    def loadProject(self, projectFile: str) -> None:
        """Load a ``.cdm3`` project from ``projectFile``."""

    def unloadProject(self, emitSignal: bool = True) -> None:
        """Unload the current project; optionally emit change notifications."""

    def createNew(self, fileName: str, props: Mapping[str, Any]) -> None:
        """Create a new project at ``fileName`` with ``props``."""

    def isLoaded(self) -> bool:
        """True when a project is currently loaded."""


BeforeLoadHook = Callable[[str], Optional[bool]]
AfterLoadHook = Callable[[str], None]
BeforeUnloadHook = Callable[[], None]
AfterUnloadHook = Callable[[], None]
ValidateLoadTarget = Callable[[str], None]
ValidateCreateTarget = Callable[[str, Mapping[str, Any]], None]


def default_prevalidate_project_load_target(project_file: str) -> None:
    """Fail closed if ``project_file`` cannot be loaded (R257).

    Checks extension, regular-file presence, and that the payload is a JSON
    object. Schema details stay in ``loadProject`` / ``load_validated_project_props``.
    """
    raw = str(project_file or "").strip()
    if not raw:
        raise ValueError("project file path is empty")
    path = os.path.abspath(os.path.expanduser(raw))
    if not path.endswith(".cdm3"):
        raise ValueError(f"unexpected project file extension (expected .cdm3): {project_file!r}")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"project file not found: {project_file}")
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"project file is not readable JSON: {project_file}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"project file must contain a JSON object: {project_file}")


def default_prevalidate_project_create_target(
    project_file: str,
    props: Mapping[str, Any],
) -> None:
    """Fail closed if a new project cannot be created at ``project_file`` (R257)."""
    del props  # reserved for future prop-shape checks
    raw = str(project_file or "").strip()
    if not raw:
        raise ValueError("project file path is empty")
    path = os.path.abspath(os.path.expanduser(raw))
    if not path.endswith(".cdm3"):
        raise ValueError(f"unexpected project file extension (expected .cdm3): {project_file!r}")
    parent = os.path.dirname(path) or os.curdir
    if not os.path.isdir(parent):
        raise FileNotFoundError(f"project parent directory not found: {parent}")
    if not os.access(parent, os.W_OK):
        raise PermissionError(f"project parent directory is not writable: {parent}")


def current_project_path(project: ProjectPort) -> str:
    """Best-effort path of the loaded project (``fileName`` / ``path`` / ``loaded_path``)."""
    for attr in ("fileName", "path", "loaded_path"):
        value = getattr(project, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


class ApplicationServices:
    """Headless application services for project lifecycle.

    Owns no widgets. Callers that need Qt (cursor, tab close confirmation)
    inject behaviour via the optional hooks; the façade only sequences
    hooks around the project port.

    R236: create / load / switch / unload all go through this façade so
    ``before_unload`` / ``after_load`` (e.g. LanguageServiceManager detach /
    attach) always run when replacing a project.

    R257: pre-validate the target before unload; on ``loadProject`` /
    ``createNew`` / ``after_load`` failure restore the previous project
    (reload + ``after_load``) when one was loaded.
    """

    def __init__(
        self,
        project: ProjectPort,
        *,
        before_load: Optional[BeforeLoadHook] = None,
        after_load: Optional[AfterLoadHook] = None,
        before_unload: Optional[BeforeUnloadHook] = None,
        after_unload: Optional[AfterUnloadHook] = None,
        prevalidate: bool = False,
        validate_load_target: Optional[ValidateLoadTarget] = None,
        validate_create_target: Optional[ValidateCreateTarget] = None,
    ) -> None:
        """Bind a project port and optional lifecycle hooks.

        ``before_load`` may return ``False`` to abort loading (other falsy
        values are treated as allow for convenience with ``None``).

        When ``prevalidate`` is true, load/create targets are checked before
        unloading the current project (enabled for the IDE façade in
        ``GlobalData``). Unit tests with in-memory ports leave it false.
        """
        self._project = project
        self._before_load = before_load
        self._after_load = after_load
        self._before_unload = before_unload
        self._after_unload = after_unload
        self._prevalidate = bool(prevalidate)
        self._validate_load_target = validate_load_target or default_prevalidate_project_load_target
        self._validate_create_target = validate_create_target or default_prevalidate_project_create_target

    @property
    def project(self) -> ProjectPort:
        """Injected project port."""
        return self._project

    @property
    def project_loaded(self) -> bool:
        """True when the bound project reports loaded."""
        return bool(self._project.isLoaded())

    def _run_after_load(self, project_file: str) -> None:
        if self._after_load is not None:
            self._after_load(project_file)

    def _restore_previous_project(self, previous: str) -> None:
        """Best-effort reload of ``previous`` after a failed switch (R257)."""
        try:
            if self._project.isLoaded():
                # Drop the failed/partial new project without after_unload side
                # effects that assume a successful detach of the old one.
                try:
                    self._project.unloadProject(False)
                except Exception:  # noqa: BLE001 — continue restore
                    logging.exception("R257: unload of failed project before restore failed")
            self._project.loadProject(previous)
            try:
                self._run_after_load(previous)
            except Exception:  # noqa: BLE001 — project restored; hook failure is secondary
                logging.exception("R257: after_load failed while restoring %s", previous)
        except Exception:
            logging.exception("R257: failed to restore previous project %s", previous)
            raise

    def load_project(self, project_file: str) -> bool:
        """Load ``project_file`` via the project port.

        R251: ``before_load`` runs **before** unloading the current project so a
        veto cannot leave an empty workspace.

        R257: pre-validate the target before unload; on load / ``after_load``
        failure restore the previous project when one was loaded.

        Returns:
            ``False`` if ``before_load`` aborted; ``True`` after a successful
            ``loadProject`` call (and ``after_load`` when set).
        """
        if self._before_load is not None:
            decision = self._before_load(project_file)
            if decision is False:
                return False

        previous = current_project_path(self._project) if self._project.isLoaded() else ""

        if self._prevalidate:
            self._validate_load_target(project_file)

        if self._project.isLoaded():
            self.unload_project()

        try:
            self._project.loadProject(project_file)
            self._run_after_load(project_file)
        except Exception:
            if previous:
                self._restore_previous_project(previous)
            raise
        return True

    def switch_project(self, project_file: str) -> bool:
        """Replace the current project with ``project_file`` (R236 / R251 / R257).

        Equivalent to :meth:`load_project` (validate-before-unload + rollback).
        """
        return self.load_project(project_file)

    def create_project(self, project_file: str, props: Mapping[str, Any]) -> bool:
        """Create a new project and run the same load lifecycle hooks (R236 / R257).

        ``before_load`` and create-target prevalidation run before unload so
        abort / invalid targets keep the previous project.
        """
        if self._before_load is not None:
            decision = self._before_load(project_file)
            if decision is False:
                return False

        previous = current_project_path(self._project) if self._project.isLoaded() else ""

        if self._prevalidate:
            self._validate_create_target(project_file, props)

        if self._project.isLoaded():
            self.unload_project()

        try:
            self._project.createNew(project_file, props)
            self._run_after_load(project_file)
        except Exception:
            if previous:
                self._restore_previous_project(previous)
            raise
        return True

    def unload_project(self, *, emit_signal: bool = True) -> None:
        """Unload the current project via the project port."""
        if self._before_unload is not None:
            self._before_unload()
        self._project.unloadProject(emit_signal)
        if self._after_unload is not None:
            self._after_unload()
