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

from ui.qt import QByteArray, QProcess, QProcessEnvironment, QWidget, pyqtSignal
from utils.misc import getLocaleDateTime
from utils.run import getProjectPythonPath


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

        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.SeparateChannels)
        self._process.setWorkingDirectory(os.path.dirname(self._fileName))
        self._process.readyReadStandardOutput.connect(self._readStdOutput)
        self._process.readyReadStandardError.connect(self._readStdError)
        self._process.finished.connect(self._finished)

        self._stdout = ""
        self._stderr = ""
        self._args = self.buildArgs(fileName)

        processEnvironment = QProcessEnvironment()
        processEnvironment.insert("PYTHONIOENCODING", self._encoding)
        self._process.setProcessEnvironment(processEnvironment)
        self._pythonPath = getProjectPythonPath(self._ide.project)
        self._process.start(self._pythonPath, self._args)

        if not self._process.waitForStarted():
            self._process = None
            return "Process failed to start"
        return None

    def stop(self):
        """Interrupts the analysis."""
        if self._process is not None:
            if self._process.state() == QProcess.Running:
                self._process.kill()
                self._process.waitForFinished()
            self._process = None
            self._args = None

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
        self._process = None

        results = {
            "ExitCode": exitCode,
            "ExitStatus": exitStatus,
            "FileName": self._fileName,
            "Timestamp": getLocaleDateTime(),
            "CommandLine": [self._pythonPath] + self._args,
            "Diagnostics": [],
            "StdOut": self._stdout,
            "StdErr": self._stderr,
        }

        if self._stderr and not self._stdout.strip():
            results["ProcessError"] = "Error:\n" + self._stderr
            self.sigFinished.emit(results)
            self._args = None
            return

        self.parseOutput(self._stdout, self._stderr, results)
        self.sigFinished.emit(results)
        self._args = None
