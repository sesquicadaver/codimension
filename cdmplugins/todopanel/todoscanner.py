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

"""TODO/FIXME/XXX/HACK scanner.

Scans Python files for marker comments. No external dependencies.
"""

import os.path
import re

# Match TODO, FIXME, XXX, HACK (case-insensitive) followed by optional : and text
_TODO_PATTERN = re.compile(
    r"\b(TODO|FIXME|XXX|HACK)\b\s*:?\s*(.*)$",
    re.IGNORECASE,
)


def scan_file(file_path, encoding="utf-8"):
    """Scan a single file for TODO markers.

    Returns list of dicts: {line, tag, text}
    """
    results = []
    try:
        with open(file_path, encoding=encoding, errors="replace") as f:
            for line_no, line in enumerate(f, 1):
                match = _TODO_PATTERN.search(line)
                if match:
                    tag = match.group(1).upper()
                    text = (match.group(2) or "").strip()
                    results.append(
                        {"line": line_no, "tag": tag, "text": text}
                    )
    except (OSError, UnicodeDecodeError):
        pass
    return results


def scan_project(project, encoding="utf-8"):
    """Scan project Python files for TODO markers.

    project: CodimensionProject instance with isLoaded(), getProjectDir(), filesList
    Returns list of dicts: {file, line, tag, text}
    """
    if not project.isLoaded():
        return []

    project_dir = project.getProjectDir()
    if not project_dir or not os.path.isdir(project_dir):
        return []

    all_results = []
    for item in project.filesList:
        if item.endswith(os.path.sep):
            continue
        if not item.lower().endswith(".py"):
            continue
        full_path = item if os.path.isabs(item) else os.path.normpath(
            project_dir + item
        )
        if not os.path.isfile(full_path):
            continue
        try:
            for hit in scan_file(full_path, encoding):
                hit["file"] = full_path
                all_results.append(hit)
        except Exception:
            pass
    return all_results


def scan_directory(dir_path, encoding="utf-8"):
    """Scan a directory recursively for Python files with TODO markers.

    Returns list of dicts: {file, line, tag, text}
    """
    if not dir_path or not os.path.isdir(dir_path):
        return []

    all_results = []
    for root, _dirs, files in os.walk(dir_path):
        for name in files:
            if not name.lower().endswith(".py"):
                continue
            full_path = os.path.join(root, name)
            for hit in scan_file(full_path, encoding):
                hit["file"] = full_path
                all_results.append(hit)
    return all_results


def scan_single_file(file_path, encoding="utf-8"):
    """Scan a single file for TODO markers.

    Returns list of dicts: {file, line, tag, text}
    """
    if not file_path or not os.path.isfile(file_path):
        return []
    results = []
    for hit in scan_file(file_path, encoding):
        hit["file"] = file_path
        results.append(hit)
    return results
