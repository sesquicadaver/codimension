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

"""Codimension mypy driver implementation"""

import json
import os.path

from ..lintdriverbase import LintDriverBase


class MypyDriver(LintDriverBase):
    """Mypy driver which runs mypy in the background."""

    def buildArgs(self, fileName):
        """Build mypy command args."""
        return [
            "-m",
            "mypy",
            "--output",
            "json",
            "--no-error-summary",
            os.path.basename(fileName),
        ]

    def parseOutput(self, stdout, stderr, results):
        """Parse mypy JSON output into Diagnostics."""
        del stderr
        try:
            data = json.loads(stdout) if stdout.strip() else {}
            if isinstance(data, dict):
                files = data.get("files", {})
                self_file = os.path.basename(self._fileName)
                for path, diags in files.items():
                    if path.endswith(self_file) or path == self._fileName:
                        for d in diags:
                            results["Diagnostics"].append(
                                {
                                    "code": d.get("code", ""),
                                    "message": d.get("message", ""),
                                    "line": d.get("line", 0),
                                    "column": d.get("column", 0),
                                }
                            )
                        break
        except json.JSONDecodeError:
            results["ProcessError"] = "Failed to parse mypy output"
