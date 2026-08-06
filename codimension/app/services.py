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

"""ApplicationServices — project load/unload façade without Qt widgets."""

from __future__ import annotations

from typing import Callable, Optional, Protocol


class ProjectPort(Protocol):
    """Minimal project surface used by the application façade.

    Matches ``CodimensionProject`` method names so the real project object can
    be injected later (R102) without adapters.
    """

    def loadProject(self, projectFile: str) -> None:
        """Load a ``.cdm3`` project from ``projectFile``."""

    def unloadProject(self, emitSignal: bool = True) -> None:
        """Unload the current project; optionally emit change notifications."""

    def isLoaded(self) -> bool:
        """True when a project is currently loaded."""


BeforeLoadHook = Callable[[str], Optional[bool]]
AfterLoadHook = Callable[[str], None]
BeforeUnloadHook = Callable[[], None]
AfterUnloadHook = Callable[[], None]


class ApplicationServices:
    """Headless application services for project lifecycle.

    Owns no widgets. Callers that need Qt (cursor, tab close confirmation)
    inject behaviour via the optional hooks; the façade only sequences
    hooks around the project port.
    """

    def __init__(
        self,
        project: ProjectPort,
        *,
        before_load: Optional[BeforeLoadHook] = None,
        after_load: Optional[AfterLoadHook] = None,
        before_unload: Optional[BeforeUnloadHook] = None,
        after_unload: Optional[AfterUnloadHook] = None,
    ) -> None:
        """Bind a project port and optional lifecycle hooks.

        ``before_load`` may return ``False`` to abort loading (other falsy
        values are treated as allow for convenience with ``None``).
        """
        self._project = project
        self._before_load = before_load
        self._after_load = after_load
        self._before_unload = before_unload
        self._after_unload = after_unload

    @property
    def project(self) -> ProjectPort:
        """Injected project port."""
        return self._project

    @property
    def project_loaded(self) -> bool:
        """True when the bound project reports loaded."""
        return bool(self._project.isLoaded())

    def load_project(self, project_file: str) -> bool:
        """Load ``project_file`` via the project port.

        Returns:
            ``False`` if ``before_load`` aborted; ``True`` after a successful
            ``loadProject`` call (and ``after_load`` when set).
        """
        if self._before_load is not None:
            decision = self._before_load(project_file)
            if decision is False:
                return False
        self._project.loadProject(project_file)
        if self._after_load is not None:
            self._after_load(project_file)
        return True

    def unload_project(self, *, emit_signal: bool = True) -> None:
        """Unload the current project via the project port."""
        if self._before_unload is not None:
            self._before_unload()
        self._project.unloadProject(emit_signal)
        if self._after_unload is not None:
            self._after_unload()
