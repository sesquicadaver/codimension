# -*- coding: utf-8 -*-
#
# codimension - graphics python two-way code editor and analyzer
# Copyright (C) 2010-2017  Sergey Satskiy <sergey.satskiy@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

"""Venv-related helpers. Kept separate to avoid circular imports."""

import os


def resolveVenvToPython(venv_dir):
    """Resolves venv directory to python executable.

    Supports: venv/bin/python (Linux), venv/Scripts/python.exe (Windows).
    """
    if not venv_dir or not os.path.isdir(venv_dir):
        return None

    for candidate in (
        os.path.join(venv_dir, "bin", "python"),
        os.path.join(venv_dir, "bin", "python3"),
        os.path.join(venv_dir, "Scripts", "python.exe"),
    ):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return os.path.abspath(candidate)
    return None


def getProjectVenvDir(project):
    """Returns the venv directory path for exclusion from project scan, or None.

    Uses pythoninterpreter from project props. Returns absolute path to venv
    directory (e.g. /proj/venv) so it can be excluded from file analysis.
    """
    if project is None or not project.isLoaded():
        return None

    interp = project.props.get("pythoninterpreter", "").strip()
    project_dir = project.getProjectDir()

    if interp:
        if not os.path.isabs(interp) and project_dir:
            interp = os.path.normpath(project_dir + interp)
        if os.path.isfile(interp) and os.access(interp, os.X_OK):
            # interp is python executable -> get venv dir
            bin_dir = os.path.dirname(os.path.abspath(interp))
            if os.path.basename(bin_dir) in ("bin", "Scripts"):
                return os.path.dirname(bin_dir)
            return None
        if os.path.isdir(interp):
            if resolveVenvToPython(interp):
                return os.path.abspath(interp)
            return None
        return None

    # Auto-detect: try .venv, venv, env in project root
    if project_dir:
        for venv_name in (".venv", "venv", "env"):
            venv_path = os.path.join(project_dir, venv_name)
            if resolveVenvToPython(venv_path):
                return os.path.abspath(venv_path)
    return None
