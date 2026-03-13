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

"""Codimension ruff driver implementation"""

import json
import os.path

from cdmplugins.lintdriverbase import LintDriverBase


class RuffDriver(LintDriverBase):
    """Ruff driver which runs ruff check in the background."""

    def buildArgs(self, fileName):
        """Build ruff check command args."""
        return [
            "-m",
            "ruff",
            "check",
            "--output-format",
            "json",
            os.path.basename(fileName),
        ]

    def parseOutput(self, stdout, stderr, results):
        """Parse ruff JSON output into Diagnostics."""
        del stderr
        try:
            data = json.loads(stdout) if stdout.strip() else []
            for diag in data:
                loc = diag.get("location", {})
                end_loc = diag.get("end_location", loc)
                results["Diagnostics"].append(
                    {
                        "code": diag.get("code", ""),
                        "message": diag.get("message", ""),
                        "filename": diag.get("filename", ""),
                        "line": loc.get("row", 0),
                        "column": loc.get("column", 0),
                        "end_line": end_loc.get("row", 0),
                        "end_column": end_loc.get("column", 0),
                    }
                )
        except json.JSONDecodeError:
            results["ProcessError"] = "Failed to parse ruff output"
