# -*- coding: utf-8 -*-
#
# codimension - AI background task driver (Qt)
# Copyright (C) 2026  Codimension Team
# The license is described in the LICENSE file at the root directory.
#

"""Run :func:`core.ai_ui.run_ai_task` off the GUI thread."""

from __future__ import annotations

from core.ai_tasks import AiTaskRequest, AiTaskResult
from core.ai_ui import run_ai_task

from .qt import QObject, QThread, pyqtSignal


class _AiTaskWorker(QObject):
    """Worker that executes one AI task."""

    sigProgress = pyqtSignal(str)
    sigFinished = pyqtSignal(object)
    sigFailed = pyqtSignal(str)

    def __init__(self, request: AiTaskRequest):
        QObject.__init__(self)
        self.__request = request

    def run(self) -> None:
        """Execute the task and emit result or error text."""
        try:

            def _progress(msg: str) -> None:
                self.sigProgress.emit(msg)

            result = run_ai_task(self.__request, progress=_progress)
            self.sigFinished.emit(result)
        except Exception as exc:
            self.sigFailed.emit(str(exc) or exc.__class__.__name__)


class AiTaskDriver(QObject):
    """Starts AI tasks in a background QThread (TodoPanel-style)."""

    sigProgress = pyqtSignal(str)
    sigFinished = pyqtSignal(object)
    sigFailed = pyqtSignal(str)

    def __init__(self, parent=None):
        QObject.__init__(self, parent)
        self.__thread = None
        self.__worker = None

    def isInProcess(self) -> bool:
        """True while a background AI task is running."""
        return self.__thread is not None and self.__thread.isRunning()

    def start(self, request: AiTaskRequest) -> str | None:
        """Start ``request``. Returns an error string if already busy."""
        if self.isInProcess():
            return "An AI task is already running"
        self.__worker = _AiTaskWorker(request)
        self.__thread = QThread(self)
        self.__worker.moveToThread(self.__thread)
        self.__thread.started.connect(self.__worker.run)
        self.__worker.sigProgress.connect(self.sigProgress)
        self.__worker.sigFinished.connect(self.__onFinished)
        self.__worker.sigFailed.connect(self.__onFailed)
        self.__worker.sigFinished.connect(self.__thread.quit)
        self.__worker.sigFailed.connect(self.__thread.quit)
        self.__thread.finished.connect(self.__onThreadFinished)
        self.__thread.start()
        return None

    def __onFinished(self, result: AiTaskResult) -> None:
        self.sigFinished.emit(result)

    def __onFailed(self, message: str) -> None:
        self.sigFailed.emit(message)

    def __onThreadFinished(self) -> None:
        try:
            self.__thread.finished.disconnect(self.__onThreadFinished)
        except TypeError:
            pass
        self.__worker = None
        self.__thread = None
