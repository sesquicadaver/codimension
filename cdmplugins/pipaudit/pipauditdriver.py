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

"""Codimension pip-audit driver implementation.

Runs pip-audit to check installed packages for known vulnerabilities.
Audits the current Python environment (venv).
"""

import json
import os.path
import sys

from ui.qt import QByteArray, QProcess, QProcessEnvironment, QWidget, pyqtSignal
from utils.misc import getLocaleDateTime
from utils.run import getProjectPythonPath


class PipAuditDriver(QWidget):
    """pip-audit driver which runs pip-audit in the background."""

    sigFinished = pyqtSignal(dict)

    def __init__(self, ide):
        QWidget.__init__(self)
        self.__ide = ide
        self.__process = None
        self.__args = None
        self.__pythonPath = sys.executable
        self.__stdout = ""
        self.__stderr = ""
        self.__encoding = "utf-8"

    def isInProcess(self):
        """True if pip-audit is still running."""
        return self.__process is not None

    def start(self, workDir=None, encoding=None):
        """Runs the pip-audit process.

        workDir: directory to run from (e.g. project root). None = current.
        encoding: output encoding. None = utf-8.
        """
        if self.__process is not None:
            return "Another pip-audit run is in progress"

        self.__encoding = "utf-8" if encoding is None else encoding
        cwd = workDir if workDir and os.path.isdir(workDir) else os.getcwd()

        self.__process = QProcess(self)
        self.__process.setProcessChannelMode(QProcess.SeparateChannels)
        self.__process.setWorkingDirectory(cwd)
        self.__process.readyReadStandardOutput.connect(self.__readStdOutput)
        self.__process.readyReadStandardError.connect(self.__readStdError)
        self.__process.finished.connect(self.__finished)

        self.__stdout = ""
        self.__stderr = ""

        self.__args = ["-m", "pip_audit", "--format", "json"]

        processEnvironment = QProcessEnvironment()
        processEnvironment.insert("PYTHONIOENCODING", self.__encoding)
        self.__process.setProcessEnvironment(processEnvironment)
        self.__pythonPath = getProjectPythonPath(self.__ide.project)
        self.__process.start(self.__pythonPath, self.__args)

        if not self.__process.waitForStarted():
            self.__process = None
            return "pip-audit failed to start"
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
            "Timestamp": getLocaleDateTime(),
            "CommandLine": [self.__pythonPath] + self.__args,
            "Packages": [],
            "StdOut": self.__stdout,
            "StdErr": self.__stderr,
        }

        if self.__stderr and not self.__stdout.strip():
            results["ProcessError"] = "pip-audit error:\n" + self.__stderr
            self.sigFinished.emit(results)
            self.__args = None
            return

        try:
            data = json.loads(self.__stdout) if self.__stdout.strip() else {}
            for dep in data.get("dependencies", []):
                name = dep.get("name", "")
                version = dep.get("version", dep.get("skip_reason", ""))
                vulns = dep.get("vulns", [])
                if vulns:
                    for v in vulns:
                        results["Packages"].append(
                            {
                                "name": name,
                                "version": version,
                                "cve": v.get("id", ""),
                                "fix_versions": v.get("fix_versions", []),
                                "description": v.get("description", ""),
                            }
                        )
        except json.JSONDecodeError:
            results["ProcessError"] = "Failed to parse pip-audit output"

        self.sigFinished.emit(results)
        self.__args = None
