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

"""Codimension pytest driver implementation"""

import os.path
import re
import sys

from ui.qt import QByteArray, QProcess, QProcessEnvironment, QWidget, pyqtSignal
from utils.misc import getLocaleDateTime
from utils.run import getProjectPythonPath


class PytestDriver(QWidget):
    """Pytest driver which runs pytest in the background."""

    sigFinished = pyqtSignal(dict)

    def __init__(self, ide):
        QWidget.__init__(self)
        self.__ide = ide
        self.__process = None
        self.__args = None
        self.__pythonPath = sys.executable
        self.__stdout = ""
        self.__stderr = ""
        self.__fileName = ""
        self.__encoding = "utf-8"

    def isInProcess(self):
        """True if pytest is still running."""
        return self.__process is not None

    def start(self, fileName, encoding):
        """Runs the pytest process."""
        if self.__process is not None:
            return "Another pytest run is in progress"

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
            "pytest",
            "-v",
            "--tb=short",
            os.path.basename(self.__fileName),
        ]

        processEnvironment = QProcessEnvironment()
        processEnvironment.insert("PYTHONIOENCODING", self.__encoding)
        self.__process.setProcessEnvironment(processEnvironment)
        self.__pythonPath = getProjectPythonPath(self.__ide.project)
        self.__process.start(self.__pythonPath, self.__args)

        if not self.__process.waitForStarted():
            self.__process = None
            return "pytest failed to start"
        return None

    def stop(self):
        """Interrupts the run."""
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
            "Timestamp": getLocaleDateTime(),
            "CommandLine": [self.__pythonPath] + self.__args,
            "Tests": [],
            "StdOut": self.__stdout,
            "StdErr": self.__stderr,
        }

        # Parse pytest output: PASSED, FAILED, ERROR lines
        for line in self.__stdout.splitlines():
            if " PASSED" in line or " FAILED" in line or " ERROR" in line:
                match = re.match(r"^(.+?)\s+(PASSED|FAILED|ERROR)", line)
                if match:
                    results["Tests"].append(
                        {
                            "name": match.group(1).strip(),
                            "status": match.group(2),
                        }
                    )

        self.sigFinished.emit(results)
        self.__args = None
