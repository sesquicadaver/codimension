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

"""Codimension coverage driver implementation.

Runs pytest with pytest-cov to collect coverage data.
Uses --cov-report=json:<file> and parses coverage.py JSON format.
"""

import json
import os.path
import tempfile

from ui.qt import QByteArray, QProcess, QProcessEnvironment, QWidget, pyqtSignal
from utils.misc import getLocaleDateTime
from utils.run import getProjectPythonPath


class CoverageDriver(QWidget):
    """Coverage driver which runs pytest with coverage in the background."""

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
        self.__covReportPath = None

    def isInProcess(self):
        """True if coverage run is still in progress."""
        return self.__process is not None

    def start(self, fileName, encoding):
        """Runs pytest with coverage."""
        if self.__process is not None:
            return "Another coverage run is in progress"

        self.__fileName = fileName
        self.__encoding = "utf-8" if encoding is None else encoding
        workDir = os.path.dirname(self.__fileName)

        fd, self.__covReportPath = tempfile.mkstemp(suffix=".coverage.json")
        os.close(fd)

        self.__process = QProcess(self)
        self.__process.setProcessChannelMode(QProcess.SeparateChannels)
        self.__process.setWorkingDirectory(workDir)
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
            "--cov=.",
            "--cov-report=json:" + self.__covReportPath,
            "--no-cov-on-fail",
            os.path.basename(self.__fileName),
        ]

        processEnvironment = QProcessEnvironment()
        processEnvironment.insert("PYTHONIOENCODING", self.__encoding)
        self.__process.setProcessEnvironment(processEnvironment)
        self.__pythonPath = getProjectPythonPath(self.__ide.project)
        self.__process.start(self.__pythonPath, self.__args)

        if not self.__process.waitForStarted():
            self.__process = None
            self.__cleanupCovReport()
            return "Coverage run failed to start"
        return None

    def stop(self):
        """Interrupts the run."""
        if self.__process is not None:
            if self.__process.state() == QProcess.Running:
                self.__process.kill()
                self.__process.waitForFinished()
            self.__process = None
            self.__cleanupCovReport()
            self.__args = None

    def __cleanupCovReport(self):
        """Removes temporary coverage report file."""
        if self.__covReportPath and os.path.exists(self.__covReportPath):
            try:
                os.unlink(self.__covReportPath)
            except OSError:
                pass
        self.__covReportPath = None

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
            "Files": [],
            "Totals": {},
            "StdOut": self.__stdout,
            "StdErr": self.__stderr,
        }

        if self.__covReportPath and os.path.exists(self.__covReportPath):
            try:
                with open(self.__covReportPath, encoding="utf-8") as f:
                    covData = json.load(f)
                results["Totals"] = covData.get("totals", {})
                filesData = covData.get("files", {})
                workDir = os.path.dirname(self.__fileName)
                for filePath, fileInfo in filesData.items():
                    summary = fileInfo.get("summary", {})
                    percent = summary.get("percent_covered", 0)
                    numStmt = summary.get("num_statements", 0)
                    covered = summary.get("covered_lines", 0)
                    missing = fileInfo.get("missing_lines", [])
                    absPath = filePath
                    if not os.path.isabs(filePath):
                        absPath = os.path.normpath(os.path.join(workDir, filePath))
                    results["Files"].append(
                        {
                            "path": absPath,
                            "percent": percent,
                            "num_statements": numStmt,
                            "covered_lines": covered,
                            "missing_lines": missing,
                        }
                    )
                results["Files"].sort(key=lambda x: (-x["percent"], x["path"]))
            except (json.JSONDecodeError, OSError) as exc:
                results["ProcessError"] = f"Failed to parse coverage: {exc}"
            finally:
                self.__cleanupCovReport()
        else:
            if exitCode != 0 and self.__stderr:
                results["ProcessError"] = "Coverage run failed:\n" + self.__stderr.strip()
            else:
                results["ProcessError"] = "No coverage data produced"

        self.sigFinished.emit(results)
        self.__args = None
