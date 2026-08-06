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

"""Base class for lint drivers (ruff, bandit, mypy).

Provides common QProcess lifecycle, stdout/stderr capture, and result structure.
Subclasses implement buildArgs() and parseOutput().
"""

import os.path

from ui.qt import QByteArray, QProcess, QTimer, QWidget, pyqtSignal
from utils.misc import getLocaleDateTime

from cdmplugins.process_env import resolve_tool_python_and_environment

# Terminate grace period before kill (ms) — avoids sync waitForFinished in GUI.
_STOP_KILL_TIMEOUT_MS = 2000


class LintDriverBase(QWidget):
    """Base for single-file Python linter drivers with JSON output.

    Subclasses must implement:
      - buildArgs(fileName) -> list of str
      - parseOutput(stdout, stderr, baseResults) -> None (modifies baseResults)
    """

    sigFinished = pyqtSignal(dict)

    def __init__(self, ide):
        QWidget.__init__(self)
        self._ide = ide
        self._process = None
        self._args = None
        self._pythonPath = None
        self._stdout = ""
        self._stderr = ""
        self._fileName = ""
        self._encoding = "utf-8"
        self._stopTimer = None
        self._processError = None

    def isInProcess(self):
        """True if the linter is still running."""
        return self._process is not None

    def buildArgs(self, fileName):
        """Build command-line args. Override in subclass."""
        raise NotImplementedError

    def parseOutput(self, stdout, stderr, results):
        """Parse stdout/stderr into results. Override in subclass."""
        raise NotImplementedError

    def start(self, fileName, encoding):
        """Runs the linter process. Returns error message or None."""
        if self._process is not None:
            return "Another analysis is in progress"

        self._fileName = fileName
        self._encoding = "utf-8" if encoding is None else encoding
        self._processError = None

        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.SeparateChannels)
        self._process.setWorkingDirectory(os.path.dirname(self._fileName))
        self._process.readyReadStandardOutput.connect(self._readStdOutput)
        self._process.readyReadStandardError.connect(self._readStdError)
        self._process.finished.connect(self._finished)
        if hasattr(self._process, "errorOccurred"):
            self._process.errorOccurred.connect(self._onProcessError)

        self._stdout = ""
        self._stderr = ""
        self._args = self.buildArgs(fileName)

        self._pythonPath, processEnvironment = resolve_tool_python_and_environment(
            self._ide.project, self._encoding
        )
        self._process.setProcessEnvironment(processEnvironment)
        self._process.start(self._pythonPath, self._args)

        if not self._process.waitForStarted():
            self._process = None
            return "Process failed to start"
        return None

    def stop(self):
        """Request cancel: terminate, then kill after timeout (non-blocking)."""
        if self._process is None:
            return
        if self._process.state() != QProcess.Running:
            self._clearProcess()
            return
        self._process.terminate()
        if self._stopTimer is not None:
            self._stopTimer.stop()
        self._stopTimer = QTimer(self)
        self._stopTimer.setSingleShot(True)
        self._stopTimer.timeout.connect(self._forceKillIfStillRunning)
        self._stopTimer.start(_STOP_KILL_TIMEOUT_MS)

    def _forceKillIfStillRunning(self):
        """Kill the process if terminate did not finish in time."""
        if self._process is not None and self._process.state() == QProcess.Running:
            self._process.kill()

    def _clearProcess(self):
        """Drop process handle and stop timer."""
        if self._stopTimer is not None:
            self._stopTimer.stop()
            self._stopTimer = None
        self._process = None
        self._args = None

    def _onProcessError(self, error):
        """Record QProcess error for the finished payload."""
        self._processError = error

    def _readStdOutput(self):
        """Handles reading from stdout."""
        self._process.setReadChannel(QProcess.StandardOutput)
        qba = QByteArray()
        while self._process.bytesAvailable():
            qba += self._process.readAllStandardOutput()
        if qba.size():
            self._stdout += qba.data().decode(self._encoding, errors="replace")

    def _readStdError(self):
        """Handles reading from stderr."""
        self._process.setReadChannel(QProcess.StandardError)
        qba = QByteArray()
        while self._process.bytesAvailable():
            qba += self._process.readAllStandardError()
        if qba.size():
            self._stderr += qba.data().decode(self._encoding, errors="replace")

    def _finished(self, exitCode, exitStatus):
        """Handles the process finish."""
        if self._stopTimer is not None:
            self._stopTimer.stop()
            self._stopTimer = None
        self._process = None

        results = {
            "ExitCode": exitCode,
            "ExitStatus": exitStatus,
            "FileName": self._fileName,
            "Timestamp": getLocaleDateTime(),
            "CommandLine": [self._pythonPath] + (self._args or []),
            "Diagnostics": [],
            "StdOut": self._stdout,
            "StdErr": self._stderr,
        }
        if self._processError is not None:
            results["QProcessError"] = self._processError

        if self._stderr and not self._stdout.strip():
            results["ProcessError"] = "Error:\n" + self._stderr
            self.sigFinished.emit(results)
            self._args = None
            return

        self.parseOutput(self._stdout, self._stderr, results)
        self.sigFinished.emit(results)
        self._args = None
