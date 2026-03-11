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

"""Codimension ruff format driver implementation.

Runs ruff format to format Python code in-place.
No separate result tab — success/error shown in status bar.
"""

import os.path
import sys

from ui.qt import QByteArray, QProcess, QProcessEnvironment, QWidget, pyqtSignal


class RuffFormatDriver(QWidget):
    """Ruff format driver which runs ruff format in the background."""

    sigFinished = pyqtSignal(dict)

    def __init__(self, ide):
        QWidget.__init__(self)
        self.__ide = ide
        self.__process = None
        self.__args = None
        self.__stdout = ""
        self.__stderr = ""
        self.__fileName = ""
        self.__encoding = "utf-8"

    def isInProcess(self):
        """True if ruff format is still running."""
        return self.__process is not None

    def start(self, fileName, encoding):
        """Runs ruff format on the file. Modifies file in-place."""
        if self.__process is not None:
            return "Another format run is in progress"

        self.__fileName = fileName
        self.__encoding = "utf-8" if encoding is None else encoding

        self.__process = QProcess(self)
        self.__process.setProcessChannelMode(QProcess.SeparateChannels)
        self.__process.setWorkingDirectory(os.path.dirname(self.__fileName))
        self.__process.readyReadStandardOutput.connect(self.__readStdOutput)
        self.__process.readyReadStandardError.connect(self.__readStdError)
        self.__process.finished.connect(self.__finished)

        self.__stdout = ""
        self.__stderr = ""

        self.__args = [
            "-m",
            "ruff",
            "format",
            os.path.basename(self.__fileName),
        ]

        processEnvironment = QProcessEnvironment()
        processEnvironment.insert("PYTHONIOENCODING", self.__encoding)
        self.__process.setProcessEnvironment(processEnvironment)
        self.__process.start(sys.executable, self.__args)

        if not self.__process.waitForStarted():
            self.__process = None
            return "ruff format failed to start"
        return None

    def stop(self):
        """Interrupts the format run."""
        if self.__process is not None:
            if self.__process.state() == QProcess.Running:
                self.__process.kill()
                self.__process.waitForFinished()
            self.__process = None
            self.__args = None

    def __readStdOutput(self):
        """Handles reading from stdout."""
        self.__process.setReadChannel(QProcess.StandardOutput)
        qba = QByteArray()
        while self.__process.bytesAvailable():
            qba += self.__process.readAllStandardOutput()
        if qba.size():
            self.__stdout += qba.data().decode(self.__encoding, errors="replace")

    def __readStdError(self):
        """Handles reading from stderr."""
        self.__process.setReadChannel(QProcess.StandardError)
        qba = QByteArray()
        while self.__process.bytesAvailable():
            qba += self.__process.readAllStandardError()
        if qba.size():
            self.__stderr += qba.data().decode(self.__encoding, errors="replace")

    def __finished(self, exitCode, exitStatus):
        """Handles the process finish."""
        self.__process = None

        results = {
            "ExitCode": exitCode,
            "ExitStatus": exitStatus,
            "FileName": self.__fileName,
            "StdOut": self.__stdout,
            "StdErr": self.__stderr,
        }

        if exitCode != 0 and self.__stderr:
            results["ProcessError"] = "ruff format error:\n" + self.__stderr.strip()
        elif self.__stderr and not self.__stdout:
            results["ProcessError"] = "ruff format:\n" + self.__stderr.strip()

        self.sigFinished.emit(results)
        self.__args = None
