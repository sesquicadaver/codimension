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

from cdmplugins.lintdriverbase import LintDriverBase


class BanditDriver(LintDriverBase):
    """Bandit driver which runs bandit in the background."""

    def buildArgs(self, fileName):
        """Build bandit command args. -q: quiet for JSON output."""
        try:
            from .banditconfig import load_extra_args
            extra = load_extra_args()
        except ImportError:
            extra = []
        return [
            "-m",
            "bandit",
            "-f",
            "json",
            "-q",
        ] + extra + [os.path.basename(fileName)]

    def parseOutput(self, stdout, stderr, results):
        """Parse bandit JSON output into Diagnostics."""
        del stderr
        try:
            data = json.loads(stdout) if stdout.strip() else {}
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
