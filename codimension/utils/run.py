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
# The ideas and code samples are taken from the winpdb project.
# Credits: Nir Aides, Copyright (C) 2005-2009
#

"""Utility functions to support running scripts"""

from __future__ import annotations

import glob
import os
import shlex
import sys
from subprocess import STDOUT, check_output

from .config import DEFAULT_ENCODING
from .encoding import detectFileEncodingToRead
from .runparams import DEBUG, PROFILE, RUN


def getProjectPythonPath(project):
    """Returns the Python executable path for project analysis (T140).

    Delegates to ``getEffectiveProjectPython`` so props, session overlay,
    and auto-detect share one resolution chain (lint/pytest/coverage).
    """
    from .venvbootstrap import getEffectiveProjectPython

    return getEffectiveProjectPython(project)


def _debuggerClientPath(scriptName):
    """Absolute path to a client script under ``codimension/debugger/client/``.

    Resolves relative to this package (not ``sys.argv[0]``) so run/debug/profile
    work under pytest, alternate launchers, and wheel installs.
    """
    pkgRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(pkgRoot, "debugger", "client", scriptName)


def getVenvSitePackages(python_path):
    """Returns site-packages path for a venv, or None if not a venv.

    Given /path/to/venv/bin/python, returns /path/to/venv/lib/pythonX.Y/site-packages.
    """
    if not python_path or python_path == sys.executable:
        return None
    # venv/bin/python -> venv_dir
    bin_dir = os.path.dirname(python_path)
    venv_dir = os.path.dirname(bin_dir)
    if os.path.basename(bin_dir) not in ("bin", "Scripts"):
        return None
    # Find lib/pythonX.Y/site-packages or lib64/pythonX.Y/site-packages
    for lib in ("lib", "lib64"):
        pattern = os.path.join(venv_dir, lib, "python*", "site-packages")
        matches = glob.glob(pattern)
        if matches:
            return matches[0]
    return None


def resolveInterpreter(params) -> str:
    """Return the interpreter path for a run session (unquoted)."""
    if params["useInherited"]:
        return sys.executable
    custom = params["customInterpreter"]
    return sys.executable if not custom else str(custom)


def parseCommandLineArguments(cmdLine: str) -> list[str]:
    """Parse user-supplied run arguments with a platform-appropriate lexer.

    Uses :func:`shlex.split` (POSIX or non-POSIX) so quoted strings, empty
    arguments, and literals like ``*.py`` / ``$HOME`` keep correct boundaries
    (audit D03 @ 628c78d7).
    """
    if cmdLine is None:
        return []
    text = str(cmdLine).strip()
    if not text:
        return []
    posix = os.name != "nt"
    try:
        return shlex.split(text, posix=posix)
    except ValueError as exc:
        raise Exception(str(exc)) from exc


def _quote_shell_prog(argv: list[str]) -> str:
    """Join argv for embedding into a custom terminal shell string."""
    return " ".join(shlex.quote(part) for part in argv)


def _wrap_custom_terminal(argv: list[str], custom_terminal: str) -> str:
    """Embed quoted ``argv`` into the user custom-terminal template."""
    quoted_prog = _quote_shell_prog(argv)
    custom = (custom_terminal or "").strip()
    if "${prog}" in custom:
        return custom.replace("${prog}", quoted_prog)
    if custom:
        return custom + " " + quoted_prog
    return quoted_prog


def buildArgvToRun(fileName, arguments, params, tcpServerPort=None, procuuid=None) -> list[str]:
    """Build argv for run (redirected client or bare interpreter+script)."""
    interpreter = resolveInterpreter(params)
    if params["redirected"]:
        return [
            interpreter,
            _debuggerClientPath("client_cdm_run.py"),
            "--host",
            "localhost",
            "--port",
            str(tcpServerPort),
            "--procuuid",
            str(procuuid),
            "--",
            fileName,
            *arguments,
        ]
    return [interpreter, fileName, *arguments]


def buildArgvToProfile(fileName, arguments, params, tcpServerPort=None, procuuid=None) -> list[str]:
    """Build argv for profile (redirected client or bare interpreter+script)."""
    interpreter = resolveInterpreter(params)
    from .globals import GlobalData

    outfile = GlobalData().getProfileOutputPath(procuuid)
    if params["redirected"]:
        return [
            interpreter,
            _debuggerClientPath("client_cdm_profile.py"),
            "--host",
            "localhost",
            "--port",
            str(tcpServerPort),
            "--procuuid",
            str(procuuid),
            "--outfile",
            outfile,
            "--",
            fileName,
            *arguments,
        ]
    return [interpreter, fileName, *arguments]


def buildArgvToDebug(fileName, arguments, params, tcpServerPort, procuuid) -> list[str]:
    """Build argv for debug client (redirected or ``--no-redirect``)."""
    interpreter = resolveInterpreter(params)
    encoding = detectFileEncodingToRead(fileName)
    parts = [
        interpreter,
        _debuggerClientPath("client_cdm_dbg.py"),
        "--host",
        "localhost",
        "--port",
        str(tcpServerPort),
        "--procuuid",
        str(procuuid),
        "--encoding",
        encoding,
    ]

    from .settings import Settings

    debugSettings = Settings().getDebuggerSettings()
    if not debugSettings.reportExceptions:
        parts.append("--no-exc-report")
    if debugSettings.traceInterpreter:
        parts.append("--trace-python")
    if debugSettings.autofork:
        if debugSettings.followChild:
            parts.append("--fork-child")
        else:
            parts.append("--fork-parent")
    if not Settings()["calltrace"]:
        parts.append("--no-call-trace")

    if not params["redirected"]:
        parts.append("--no-redirect")
    parts.extend(["--", fileName, *arguments])
    return parts


def getTerminalCommandToRun(fileName, arguments, params, tcpServerPort=None, procuuid=None):
    """Shell string for custom-terminal run (legacy callers / non-redirected)."""
    argv = buildArgvToRun(fileName, arguments, params, tcpServerPort, procuuid)
    if params["redirected"]:
        return _quote_shell_prog(argv)
    return _wrap_custom_terminal(argv, params["customTerminal"])


def getTerminalCommandToProfile(fileName, arguments, params, tcpServerPort=None, procuuid=None):
    """Shell string for custom-terminal profile (legacy callers / non-redirected)."""
    argv = buildArgvToProfile(fileName, arguments, params, tcpServerPort, procuuid)
    if params["redirected"]:
        return _quote_shell_prog(argv)
    return _wrap_custom_terminal(argv, params["customTerminal"])


def getTerminalCommandToDebug(fileName, arguments, params, tcpServerPort, procuuid):
    """Shell string for custom-terminal debug (legacy callers / non-redirected)."""
    argv = buildArgvToDebug(fileName, arguments, params, tcpServerPort, procuuid)
    if params["redirected"]:
        return _quote_shell_prog(argv)
    return _wrap_custom_terminal(argv, params["customTerminal"])


def getCwdCmdEnv(kind, path, params, tcpServerPort=None, procuuid=None):
    """Provide command, environment, and shell flag for run/profile/debug.

    Redirected sessions return ``(argv: list[str], env, False)`` so
    ``Popen(..., shell=False)`` preserves argument boundaries (audit D03).

    Custom-terminal sessions return ``(cmd: str, env, True)`` with each argv
    element passed through :func:`shlex.quote` before embedding into the
    terminal template (explicit shell contract; not shared with redirected).
    """
    if kind not in [RUN, PROFILE, DEBUG]:
        raise Exception("Unknown command requested. Supported command types are: run, profile, debug.")

    arguments = parseCommandLineArguments(params["arguments"])
    if kind == RUN:
        argv = buildArgvToRun(path, arguments, params, tcpServerPort, procuuid)
    elif kind == PROFILE:
        argv = buildArgvToProfile(path, arguments, params, tcpServerPort, procuuid)
    else:
        argv = buildArgvToDebug(path, arguments, params, tcpServerPort, procuuid)

    environment = getNoArgsEnvironment(params)

    if params["redirected"]:
        return argv, environment, False

    return _wrap_custom_terminal(argv, params["customTerminal"]), environment, True


def getNoArgsEnvironment(params):
    """Provides a copy of the environment"""
    if params["envType"] == params.InheritParentEnv:
        # 'None' does not work here: popen stores last env somewhere and
        # uses it inappropriately
        return os.environ.copy()
    if params["envType"] == params.InheritParentEnvPlus:
        environment = os.environ.copy()
        environment.update(params["additionToParentEnv"])
        return environment
    return params["specificEnv"].copy()


def checkOutput(cmdLine, useShell=False):
    """Wrapper around Subprocess.check_output which respects encoding"""
    if useShell:
        if not isinstance(cmdLine, str):
            raise Exception("Running via shell requires the command line as a string")
    else:
        if not isinstance(cmdLine, list):
            raise Exception("Running without shell requires the command line as a list")
    return check_output(cmdLine, stderr=STDOUT, shell=useShell).decode(DEFAULT_ENCODING)


if __name__ == "__main__":
    print("Current working dir: " + os.getcwd())
    print("Environment: " + str(os.environ))
    print("Arguments: " + str(sys.argv))
