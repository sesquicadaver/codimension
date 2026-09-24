# -*- coding: utf-8 -*-
#
# codimension - AI background task driver (Qt)
# Copyright (C) 2026  Codimension Team
# The license is described in the LICENSE file at the root directory.
#

"""Run :func:`core.ai_ui.run_ai_task` off the GUI thread.

R269: deterministic QObject/QThread lifecycle — ``deleteLater`` on worker and
thread, plus :meth:`AiTaskDriver.shutdown` (cancel → quit → wait) so MainWindow
close does not destroy a live parent while the worker thread is still running.
"""

from __future__ import annotations

from core.ai_tasks import AiTaskRequest, AiTaskResult
from core.ai_ui import run_ai_task

from .qt import QObject, QThread, pyqtSignal


class _AiTaskWorker(QObject):
    """Worker that executes one AI task."""

    sigProgress = pyqtSignal(str)
    sigFinished = pyqtSignal(object)
    sigFailed = pyqtSignal(str)

    def __init__(self, request: AiTaskRequest, *, should_cancel):
        QObject.__init__(self)
        self.__request = request
        self.__should_cancel = should_cancel

    def run(self) -> None:
        """Execute the task and emit result or error text."""
        try:

            def _progress(msg: str) -> None:
                self.sigProgress.emit(msg)

            result = run_ai_task(
                self.__request,
                progress=_progress,
                should_cancel=self.__should_cancel,
            )
            self.sigFinished.emit(result)
        except Exception as exc:
            self.sigFailed.emit(str(exc) or exc.__class__.__name__)


class AiTaskDriver(QObject):
    """Starts AI tasks in a background QThread (TodoPanel-style).

    R241: :meth:`cancel` sets a cooperative cancellation flag that is passed
    into the live HTTP backend and project-analysis loop.

    R269: worker/thread are scheduled for ``deleteLater`` on completion;
    :meth:`shutdown` cancels and waits so IDE close cannot tear down the
    parent while the thread is still running.
    """

    sigProgress = pyqtSignal(str)
    sigFinished = pyqtSignal(object)
    sigFailed = pyqtSignal(str)

    def __init__(self, parent=None):
        QObject.__init__(self, parent)
        self.__thread: QThread | None = None
        self.__worker: _AiTaskWorker | None = None
        self.__cancel_requested = False

    def isInProcess(self) -> bool:
        """True while a background AI task is running."""
        return bool(self.__thread is not None and self.__thread.isRunning())

    def cancel(self) -> None:
        """Request cooperative cancellation of the in-flight AI task (R241)."""
        self.__cancel_requested = True
        if self.__thread is not None:
            self.__thread.requestInterruption()

    def shutdown(self, timeout_ms: int = 5000) -> bool:
        """Cancel the live task and wait for the worker thread to stop (R269).

        Returns ``True`` when no thread is running afterwards (including when
        none was started). Returns ``False`` if the thread is still alive after
        ``timeout_ms`` — callers must not destroy the Qt parent tree in that
        case.
        """
        self.cancel()
        thread = self.__thread
        if thread is None:
            return True
        if thread.isRunning():
            thread.quit()
            if not thread.wait(max(0, int(timeout_ms))):
                return False
        # finished → deleteLater may still be pending; Python refs cleared in
        # :meth:`__onThreadFinished` (also invoked when wait succeeds).
        if self.__thread is thread and not thread.isRunning():
            self.__clearThreadRefs()
        return not bool(self.__thread is not None and self.__thread.isRunning())

    def start(self, request: AiTaskRequest) -> str | None:
        """Start ``request``. Returns an error string if already busy."""
        if self.isInProcess():
            return "An AI task is already running"
        self.__cancel_requested = False
        self.__worker = _AiTaskWorker(request, should_cancel=lambda: self.__cancel_requested)
        self.__thread = QThread(self)
        self.__worker.moveToThread(self.__thread)
        self.__thread.started.connect(self.__worker.run)
        self.__worker.sigProgress.connect(self.sigProgress)
        self.__worker.sigFinished.connect(self.__onFinished)
        self.__worker.sigFailed.connect(self.__onFailed)
        # R269: quit thread + schedule QObject deletion on the correct affinity.
        self.__worker.sigFinished.connect(self.__thread.quit)
        self.__worker.sigFailed.connect(self.__thread.quit)
        self.__worker.sigFinished.connect(self.__worker.deleteLater)
        self.__worker.sigFailed.connect(self.__worker.deleteLater)
        self.__thread.finished.connect(self.__thread.deleteLater)
        self.__thread.finished.connect(self.__onThreadFinished)
        self.__thread.start()
        return None

    def __onFinished(self, result: AiTaskResult) -> None:
        self.sigFinished.emit(result)

    def __onFailed(self, message: str) -> None:
        self.sigFailed.emit(message)

    def __clearThreadRefs(self) -> None:
        """Drop Python wrappers after the native thread has stopped (R269)."""
        self.__worker = None
        self.__thread = None
        self.__cancel_requested = False

    def __onThreadFinished(self) -> None:
        try:
            if self.__thread is not None:
                self.__thread.finished.disconnect(self.__onThreadFinished)
        except TypeError:
            pass
        self.__clearThreadRefs()
