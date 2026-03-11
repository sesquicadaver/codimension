# -*- coding: utf-8 -*-
#
# codimension - graphics python two-way code editor and analyzer
# Copyright (C) 2025  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Codimension TODO panel driver.

Runs TODO/FIXME/XXX/HACK scan in a background thread.
"""

import os.path

from ui.qt import QObject, QThread, pyqtSignal

from .todoscanner import scan_project, scan_directory, scan_single_file


class _TodoScanWorker(QObject):
    """Worker that runs scan in a thread."""

    sigFinished = pyqtSignal(list)

    def __init__(self, scan_fn, *args, **kwargs):
        QObject.__init__(self)
        self.__scanFn = scan_fn
        self.__args = args
        self.__kwargs = kwargs

    def run(self):
        """Executes the scan and emits results."""
        try:
            results = self.__scanFn(*self.__args, **self.__kwargs)
            self.sigFinished.emit(results)
        except Exception:
            self.sigFinished.emit([])


class TodoPanelDriver(QObject):
    """TODO panel driver. Runs scan in background thread."""

    sigFinished = pyqtSignal(list)

    def __init__(self, ide):
        QObject.__init__(self)
        self.__ide = ide
        self.__thread = None
        self.__worker = None

    def isInProcess(self):
        """True if scan is still running."""
        return self.__thread is not None and self.__thread.isRunning()

    def start(self, encoding=None):
        """Starts the TODO scan.

        Scope:
        - If project loaded: scan project files
        - Else if current file is Python: scan its directory
        - Else: scan current file only (if Python)
        """
        if self.isInProcess():
            return "Scan already in progress"

        enc = encoding or "utf-8"
        project = self.__ide.project
        editorWidget = self.__ide.currentEditorWidget
        if editorWidget and editorWidget.getEncoding():
            enc = editorWidget.getEncoding()

        if project.isLoaded():
            scan_fn = scan_project
            args = (project,)
        elif editorWidget and editorWidget.getFileName():
            fname = editorWidget.getFileName()
            if not fname.lower().endswith(".py"):
                return "Open a Python file or load a project"
            if os.path.isfile(fname):
                dir_path = os.path.dirname(fname)
                if dir_path:
                    scan_fn = scan_directory
                    args = (dir_path,)
                else:
                    scan_fn = scan_single_file
                    args = (fname,)
            else:
                return "Save the file before scanning"
        else:
            return "Open a Python file or load a project"

        self.__worker = _TodoScanWorker(scan_fn, *args, encoding=enc)
        self.__thread = QThread(self)
        self.__worker.moveToThread(self.__thread)
        self.__thread.started.connect(self.__worker.run)
        self.__worker.sigFinished.connect(self.__onFinished)
        self.__worker.sigFinished.connect(self.__thread.quit)
        self.__thread.finished.connect(self.__onThreadFinished)
        self.__thread.start()
        return None

    def __onFinished(self, results):
        """Handles scan completion."""
        self.sigFinished.emit(results)

    def __onThreadFinished(self):
        """Cleans up after thread has stopped."""
        try:
            self.__thread.finished.disconnect(self.__onThreadFinished)
        except TypeError:
            pass
        self.__worker = None
        self.__thread = None
