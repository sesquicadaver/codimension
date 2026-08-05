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
import json
import os
import re
import shlex
import sys
import tempfile
import textwrap
from subprocess import STDOUT, check_output

from .config import DEFAULT_ENCODING
from .encoding import detectFileEncodingToRead
from .runparams import DEBUG, PROFILE, RUN

# Paths embedded into ``"${prog}"`` templates must not trigger shell expansion.
_SHELL_SAFE_PATH = re.compile(r"^[A-Za-z0-9._/=+-]+$")


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


def assertShellSafePath(path: str) -> str:
    """Return absolute path or raise if unsafe inside ``"${prog}"`` templates."""
    abs_path = os.path.abspath(path)
    if not _SHELL_SAFE_PATH.match(abs_path):
        raise RuntimeError(f"path is not safe for ${{prog}} shell embedding: {abs_path}")
    return abs_path


def writeArgvLauncher(argv: list[str]) -> str:
    """Write a temp executable that runs ``argv`` via ``os.execvp`` (no shell).

    Returns a shell-safe absolute path intended as the sole ``${prog}``
    substitution (audit E01 @ 1dfb3a1d). Caller argv is stored in JSON beside
    the launcher so user arguments never enter the terminal template text.
    """
    if not argv:
        raise RuntimeError("empty argv for launcher")
    work = tempfile.mkdtemp(prefix="cdm-run-")
    argv_path = os.path.join(work, "argv.json")
    launch_path = os.path.join(work, "launch.py")
    with open(argv_path, "w", encoding="utf-8") as handle:
        json.dump([str(part) for part in argv], handle, ensure_ascii=False)
    script = textwrap.dedent(
        """\
        #!/usr/bin/env python3
        # Codimension argv launcher — do not edit; generated for one run.
        import json
        import os
        import sys
        from pathlib import Path

        argv = json.loads(Path(__file__).with_name("argv.json").read_text(encoding="utf-8"))
        if not argv:
            sys.stderr.write("empty argv\\n")
            raise SystemExit(1)
        os.execvp(argv[0], argv)
        """
    )
    with open(launch_path, "w", encoding="utf-8") as handle:
        handle.write(script)
    os.chmod(launch_path, 0o755)
    return assertShellSafePath(launch_path)


def customTerminalBackgrounds(custom_terminal: str) -> bool:
    """True when the template likely backgrounds the program (trailing ``&``)."""
    return bool(custom_terminal) and custom_terminal.rstrip().endswith("&")


def _wrap_custom_terminal(argv: list[str], custom_terminal: str) -> str:
    """Embed a single launcher path into the user custom-terminal template.

    Never joins the full argv into the template (E01): that breaks inside
    recommended ``bash -c "${prog}; …"`` double-quote contexts.
    """
    launcher = writeArgvLauncher(argv)
    custom = (custom_terminal or "").strip()
    if "${prog}" in custom:
        return custom.replace("${prog}", launcher)
    if custom:
        return custom + " " + launcher
    return launcher


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
    """Build argv for profile (redirected client or ``python -m cProfile``)."""
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
    # Custom terminal: still profile (E02) — never fall back to a bare Run.
    return [interpreter, "-m", "cProfile", "-o", outfile, fileName, *arguments]


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
        return " ".join(shlex.quote(part) for part in argv)
    return _wrap_custom_terminal(argv, params["customTerminal"])


def getTerminalCommandToProfile(fileName, arguments, params, tcpServerPort=None, procuuid=None):
    """Shell string for custom-terminal profile (legacy callers / non-redirected)."""
    argv = buildArgvToProfile(fileName, arguments, params, tcpServerPort, procuuid)
    if params["redirected"]:
        return " ".join(shlex.quote(part) for part in argv)
    return _wrap_custom_terminal(argv, params["customTerminal"])


def getTerminalCommandToDebug(fileName, arguments, params, tcpServerPort, procuuid):
    """Shell string for custom-terminal debug (legacy callers / non-redirected)."""
    argv = buildArgvToDebug(fileName, arguments, params, tcpServerPort, procuuid)
    if params["redirected"]:
        return " ".join(shlex.quote(part) for part in argv)
    return _wrap_custom_terminal(argv, params["customTerminal"])


def getCwdCmdEnv(kind, path, params, tcpServerPort=None, procuuid=None):
    """Provide command, environment, and shell flag for run/profile/debug.

    Redirected sessions return ``(argv: list[str], env, False)`` so
    ``Popen(..., shell=False)`` preserves argument boundaries (audit D03).

    Custom-terminal sessions return ``(cmd: str, env, True)`` where ``${prog}``
    is replaced by a single launcher path that ``execvp``s the real argv
    (audit E01). Profile without redirect uses ``python -m cProfile`` (E02)
    and refuses backgrounding templates that would race the profile output.
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

    custom = (params["customTerminal"] or "").strip()
    if kind == PROFILE and customTerminalBackgrounds(custom):
        raise RuntimeError(
            "Custom-terminal Profile cannot use a backgrounding template "
            "(trailing '&'). Remove '&' or enable redirected IO so profiling "
            "can finish before results are collected."
        )

    return _wrap_custom_terminal(argv, custom), environment, True


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
