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

from cdmplugins.lintdriverbase import LintDriverBase


def parse_mypy_jsonl(stdout: str, file_name: str) -> list[dict]:
    """Parse mypy ``--output json`` JSONL into diagnostic dicts (T034).

    Each non-empty line is one JSON object with keys like
    ``file``, ``line``, ``column``, ``message``, ``code``, ``severity``.
    """
    diagnostics: list[dict] = []
    self_file = os.path.basename(file_name)
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            # Legacy fabricated single-object payload (tests / old mocks)
            if not diagnostics and stdout.lstrip().startswith("{"):
                data = json.loads(stdout)
                return _parse_legacy_files_object(data, file_name)
            continue
        if not isinstance(item, dict):
            continue
        if "files" in item:
            return _parse_legacy_files_object(item, file_name)
        path = item.get("file") or item.get("path") or ""
        if path and not (path.endswith(self_file) or path == file_name or os.path.basename(path) == self_file):
            # Keep diagnostics for the active buffer; skip unrelated files
            continue
        diagnostics.append(
            {
                "code": item.get("code") or "",
                "message": item.get("message") or "",
                "line": int(item.get("line") or 0),
                "column": int(item.get("column") or 0),
                "severity": item.get("severity") or "",
                "end_line": int(item.get("end_line") or item.get("line") or 0),
                "end_column": int(item.get("end_column") or item.get("column") or 0),
            }
        )
    return diagnostics


def _parse_legacy_files_object(data: object, file_name: str) -> list[dict]:
    """Compatibility path for the obsolete ``{\"files\": {...}}`` shape."""
    diagnostics: list[dict] = []
    if not isinstance(data, dict):
        return diagnostics
    files = data.get("files", {})
    if not isinstance(files, dict):
        return diagnostics
    self_file = os.path.basename(file_name)
    for path, diags in files.items():
        if not (str(path).endswith(self_file) or path == file_name):
            continue
        for d in diags or []:
            if not isinstance(d, dict):
                continue
            diagnostics.append(
                {
                    "code": d.get("code", ""),
                    "message": d.get("message", ""),
                    "line": d.get("line", 0),
                    "column": d.get("column", 0),
                    "severity": d.get("severity", ""),
                }
            )
        break
    return diagnostics


class MypyDriver(LintDriverBase):
    """Mypy driver which runs mypy in the background."""

    def buildArgs(self, fileName):
        """Build mypy command args."""
        try:
            from .mypyconfig import load_extra_args

            extra = load_extra_args()
        except ImportError:
            extra = []
        return (
            [
                "-m",
                "mypy",
                "--output",
                "json",
                "--no-error-summary",
            ]
            + extra
            + [os.path.basename(fileName)]
        )

    def parseOutput(self, stdout, stderr, results):
        """Parse mypy JSONL (or legacy files object) into Diagnostics."""
        del stderr
        if not stdout.strip():
            return
        try:
            diags = parse_mypy_jsonl(stdout, self._fileName)
            results["Diagnostics"].extend(diags)
            if not diags and stdout.strip() and not stdout.lstrip().startswith("{"):
                results["ProcessError"] = "Failed to parse mypy output"
        except json.JSONDecodeError:
            results["ProcessError"] = "Failed to parse mypy output"
