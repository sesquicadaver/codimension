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
import stat
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


def _launcherWorkRoots() -> list[str]:
    """Trusted candidate parents for ``cdm-run-*`` work dirs (audit E06).

    Prefer Codimension settings / XDG runtime over system ``/tmp`` so launchers
    still run when ``/tmp`` is mounted ``noexec``. Do not use a reusable
    ``/tmp/cdm-run`` parent (multi-user race). Windows is still unverified.
    """
    roots: list[str] = []
    try:
        from .settings import SETTINGS_DIR

        roots.append(os.path.join(SETTINGS_DIR, "cdm-run"))
    except ImportError:
        pass
    xdg = os.environ.get("XDG_RUNTIME_DIR")
    if xdg:
        roots.append(os.path.join(xdg, "cdm-run"))
    return roots


def _isTrustedLauncherWorkRoot(path: str) -> bool:
    """True if ``path`` is a real directory owned by us with mode ``0700``.

    Uses ``lstat`` so a symlink cannot masquerade as a trusted root (F07).
    """
    try:
        st = os.lstat(path)
    except OSError:
        return False
    if not stat.S_ISDIR(st.st_mode):
        return False
    if st.st_uid != os.getuid():
        return False
    if st.st_mode & 0o077:
        return False
    return True


def _ensureLauncherWorkRoot() -> str | None:
    """Return a trusted parent for ``mkdtemp``, or ``None`` for sticky system temp.

    Existing parents that are world/group-accessible are skipped (not chmod-healed).
    Write probes use ``O_EXCL`` (+ ``O_NOFOLLOW`` when available).
    """
    import time as _time

    for root in _launcherWorkRoots():
        try:
            if os.path.lexists(root) and not _isTrustedLauncherWorkRoot(root):
                # Symlink or untrusted real dir — never heal or use.
                continue
            if not os.path.isdir(root):
                parent = os.path.dirname(root)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                try:
                    os.mkdir(root, 0o700)
                except FileExistsError:
                    if not _isTrustedLauncherWorkRoot(root):
                        continue
                else:
                    try:
                        os.chmod(root, 0o700)
                    except OSError:
                        pass
                    if not _isTrustedLauncherWorkRoot(root):
                        continue
            probe = os.path.join(root, f".cdm-write-probe-{os.getpid()}-{_time.time_ns()}")
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            fd = os.open(probe, flags, 0o600)
            try:
                os.write(fd, b"ok")
            finally:
                os.close(fd)
            os.unlink(probe)
            return root
        except OSError:
            continue
    return None


def _legacyTmpCleanupMarkerPath() -> str:
    """Marker that one-shot legacy ``/tmp`` ``cdm-run-*`` cleanup already ran."""
    try:
        from .settings import SETTINGS_DIR

        return os.path.join(SETTINGS_DIR, ".cdm-legacy-tmp-cleanup-done")
    except ImportError:
        return os.path.join(tempfile.gettempdir(), ".cdm-legacy-tmp-cleanup-done")


def _removeStaleCdmRunDir(path: str, deadline: float) -> bool:
    """Delete one aged ``cdm-run-*`` directory without following symlinks (F07).

    Requires: real directory, owned by current uid, no group/other bits, mtime
    older than ``deadline``. Children are removed via ``dir_fd`` + ``O_NOFOLLOW``.
    """
    try:
        st = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(st.st_mode):
        return False
    if not stat.S_ISDIR(st.st_mode):
        return False
    if st.st_uid != os.getuid():
        return False
    if st.st_mode & 0o077:
        return False
    if st.st_mtime > deadline:
        return False

    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        dir_fd = os.open(path, flags)
    except OSError:
        return False
    try:
        try:
            for name in os.listdir(dir_fd):
                try:
                    os.unlink(name, dir_fd=dir_fd)
                except IsADirectoryError:
                    try:
                        os.rmdir(name, dir_fd=dir_fd)
                    except OSError:
                        pass
                except OSError:
                    pass
            cur = os.fstat(dir_fd)
            if cur.st_ino != st.st_ino or cur.st_dev != st.st_dev:
                return False
        finally:
            os.close(dir_fd)
        os.rmdir(path)
        return True
    except OSError:
        return False


def cleanupStaleArgvLaunchers(max_age_seconds: float = 86400.0) -> int:
    """Remove leftover ``cdm-run-*`` dirs under trusted launcher roots (E04/F07).

    Best-effort only: races and permission errors are ignored. Returns the
    number of directories successfully removed.

    Never follows symlinks (``lstat`` / ``O_NOFOLLOW`` / ``dir_fd``). System
    ``tempfile.gettempdir()`` is scanned at most once (legacy migration), then
    a marker under ``SETTINGS_DIR`` disables further global ``/tmp`` sweeps.
    """
    import time as _time

    removed = 0
    deadline = _time.time() - max_age_seconds
    parents = list(_launcherWorkRoots())
    legacy_marker = _legacyTmpCleanupMarkerPath()
    scan_legacy_tmp = not os.path.exists(legacy_marker)
    if scan_legacy_tmp:
        parents.append(tempfile.gettempdir())

    seen: set[str] = set()
    for parent in parents:
        parent = os.path.abspath(parent)
        if parent in seen:
            continue
        seen.add(parent)
        try:
            with os.scandir(parent) as entries:
                for entry in entries:
                    if not entry.name.startswith("cdm-run-"):
                        continue
                    try:
                        if not entry.is_dir(follow_symlinks=False):
                            continue
                    except OSError:
                        continue
                    if _removeStaleCdmRunDir(entry.path, deadline):
                        removed += 1
        except OSError:
            continue

    if scan_legacy_tmp:
        try:
            marker_parent = os.path.dirname(legacy_marker)
            if marker_parent:
                os.makedirs(marker_parent, exist_ok=True)
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            fd = os.open(legacy_marker, flags, 0o600)
            try:
                os.write(fd, b"done\n")
            finally:
                os.close(fd)
        except FileExistsError:
            pass
        except OSError:
            pass
    return removed


# Bounded wait for non-redirected Profile marker ∧ outfile (E05).
# Independent of custom-terminal template text (no trailing-& heuristic).
PROFILE_COMPLETION_TIMEOUT_SEC = 3600


def getProfileCompletionMarkerPath(outfile: str) -> str:
    """Sibling completion marker path for a profile outfile (audit E05)."""
    return str(outfile) + ".done"


def profileResultsReady(outfile: str | None, marker: str | None) -> bool:
    """True when marker exists and profile outfile is non-empty (E05 fail-closed)."""
    if not outfile or not marker:
        return False
    try:
        return os.path.isfile(marker) and os.path.isfile(outfile) and os.path.getsize(outfile) > 0
    except OSError:
        return False


def cleanupProfileCompletionMarker(marker: str | None) -> None:
    """Remove a profile ``.done`` marker (and leftover ``.tmp``) after use (E05)."""
    if not marker:
        return
    for path in (marker, str(marker) + ".tmp"):
        try:
            os.unlink(path)
        except OSError:
            pass


def writeArgvLauncher(argv: list[str], *, completion_marker: str | None = None) -> str:
    """Write a temp executable that runs ``argv`` without shell expansion.

    Returns a shell-safe absolute path intended as the sole ``${prog}``
    substitution (audit E01 @ 1dfb3a1d). Caller argv is stored in JSON beside
    the launcher so user arguments never enter the terminal template text.

    The generated launcher deletes ``argv.json``, itself, and the temp
    directory after loading argv into memory (E04).

    Without ``completion_marker``, the launcher ``os.execvp``s the target
    (RUN/DEBUG). With a marker (non-redirected PROFILE, E05), it runs the
    target via ``subprocess.call``, then atomically writes the marker. In that
    mode ``${prog}`` is the wrapper PID, not the cProfile process image.

    E06: shebang uses absolute ``sys.executable`` (not ``/usr/bin/env python3``)
    and the work directory prefers settings/XDG over system ``/tmp``.
    """
    if not argv:
        raise RuntimeError("empty argv for launcher")
    cleanupStaleArgvLaunchers()
    interpreter = assertShellSafePath(sys.executable)
    work_root = _ensureLauncherWorkRoot()
    if work_root is None:
        import logging

        logging.info("Custom-terminal launcher using sticky system temp (no trusted settings/XDG work root available).")
    work = tempfile.mkdtemp(prefix="cdm-run-", dir=work_root)
    argv_path = os.path.join(work, "argv.json")
    launch_path = os.path.join(work, "launch.py")
    with open(argv_path, "w", encoding="utf-8") as handle:
        json.dump([str(part) for part in argv], handle, ensure_ascii=False)
    shebang = f"#!{interpreter}\n"
    if completion_marker:
        marker_literal = json.dumps(str(completion_marker), ensure_ascii=False)
        body = textwrap.dedent(
            f"""\
            # Codimension profile launcher — marker after child (E05); do not edit.
            import json
            import os
            import subprocess
            import sys
            from pathlib import Path

            here = Path(__file__).resolve()
            argv_path = here.with_name("argv.json")
            argv = json.loads(argv_path.read_text(encoding="utf-8"))
            if not argv:
                sys.stderr.write("empty argv\\n")
                raise SystemExit(1)
            # E04: drop argv from disk before starting the profiled process.
            for path in (argv_path, here):
                try:
                    path.unlink()
                except OSError:
                    pass
            try:
                here.parent.rmdir()
            except OSError:
                pass
            rc = subprocess.call(argv)
            marker = {marker_literal}
            tmp = marker + ".tmp"
            with open(tmp, "w", encoding="utf-8") as handle:
                handle.write("done\\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, marker)
            raise SystemExit(rc)
            """
        )
        script = shebang + body
    else:
        body = textwrap.dedent(
            """\
            # Codimension argv launcher — do not edit; generated for one run.
            import json
            import os
            import sys
            from pathlib import Path

            here = Path(__file__).resolve()
            argv_path = here.with_name("argv.json")
            argv = json.loads(argv_path.read_text(encoding="utf-8"))
            if not argv:
                sys.stderr.write("empty argv\\n")
                raise SystemExit(1)
            # E04: drop argv from disk before replacing the process image.
            for path in (argv_path, here):
                try:
                    path.unlink()
                except OSError:
                    pass
            try:
                here.parent.rmdir()
            except OSError:
                pass
            os.execvp(argv[0], argv)
            """
        )
        script = shebang + body
    with open(launch_path, "w", encoding="utf-8") as handle:
        handle.write(script)
    os.chmod(launch_path, 0o755)
    return assertShellSafePath(launch_path)


def _wrap_custom_terminal(argv: list[str], custom_terminal: str, *, completion_marker: str | None = None) -> str:
    """Embed a single launcher path into the user custom-terminal template.

    Never joins the full argv into the template (E01): that breaks inside
    recommended ``bash -c "${prog}; …"`` double-quote contexts.
    """
    launcher = writeArgvLauncher(argv, completion_marker=completion_marker)
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
    from .globals import GlobalData

    outfile = GlobalData().getProfileOutputPath(procuuid)
    marker = getProfileCompletionMarkerPath(outfile)
    return _wrap_custom_terminal(argv, params["customTerminal"], completion_marker=marker)


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
    is replaced by a single launcher path (audit E01). Profile without redirect
    uses ``python -m cProfile`` (E02) and a completion marker so results are
    not tied to terminal lifetime (E05).
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
    marker = None
    if kind == PROFILE:
        from .globals import GlobalData

        outfile = GlobalData().getProfileOutputPath(procuuid)
        marker = getProfileCompletionMarkerPath(outfile)

    return _wrap_custom_terminal(argv, custom, completion_marker=marker), environment, True


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
