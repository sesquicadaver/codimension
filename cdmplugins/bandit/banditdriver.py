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

"""Codimension Bandit driver implementation.

Runs Bandit security linter with JSON output.
"""

import json
import os.path
import sys

from ui.qt import QByteArray, QProcess, QProcessEnvironment, QWidget, pyqtSignal
from utils.misc import getLocaleDateTime


class BanditDriver(QWidget):
    """Bandit driver which runs bandit in the background."""

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
        """True if bandit is still running."""
        return self.__process is not None

    def start(self, fileName, encoding):
        """Runs the bandit process."""
        if self.__process is not None:
            return "Another bandit analysis is in progress"

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

        # -q quiet mode: no progress output that could break JSON
        self.__args = [
            "-m",
            "bandit",
            "-f",
            "json",
            "-q",
            os.path.basename(self.__fileName),
        ]

        processEnvironment = QProcessEnvironment()
        processEnvironment.insert("PYTHONIOENCODING", self.__encoding)
        self.__process.setProcessEnvironment(processEnvironment)
        self.__process.start(sys.executable, self.__args)

        if not self.__process.waitForStarted():
            self.__process = None
            return "bandit failed to start"
        return None

    def stop(self):
        """Interrupts the analysis."""
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
            "CommandLine": [sys.executable] + self.__args,
            "Diagnostics": [],
            "StdOut": self.__stdout,
            "StdErr": self.__stderr,
        }

        if self.__stderr and not self.__stdout.strip():
            results["ProcessError"] = "bandit error:\n" + self.__stderr
            self.sigFinished.emit(results)
            self.__args = None
            return

        try:
            data = json.loads(self.__stdout) if self.__stdout.strip() else {}
            for r in data.get("results", []):
                results["Diagnostics"].append(
                    {
                        "line": r.get("line_number", 0),
                        "code": r.get("test_id", ""),
                        "message": r.get("issue_text", ""),
                        "severity": r.get("issue_severity", ""),
                        "confidence": r.get("issue_confidence", ""),
                    }
                )
            if data.get("errors"):
                results["errors"] = data["errors"]
        except json.JSONDecodeError:
            results["ProcessError"] = "Failed to parse bandit output"

        self.sigFinished.emit(results)
        self.__args = None
