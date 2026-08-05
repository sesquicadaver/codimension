# -*- coding: utf-8 -*-
"""D03: redirected run/debug/profile must use argv + shell=False."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

# Ensure package-relative parsers provide cdmpyparser before utils.run import.
import parsers  # noqa: E402,F401
import pytest


def _params(**overrides):
    from utils.runparams import RunParameters

    p = RunParameters()
    for key, value in overrides.items():
        p[key] = value
    return p


def test_parse_preserves_argument_boundaries():
    from utils.run import parseCommandLineArguments

    assert parseCommandLineArguments('"hello world"') == ["hello world"]
    assert parseCommandLineArguments('""') == [""]
    assert parseCommandLineArguments("*.py") == ["*.py"]
    assert parseCommandLineArguments("$HOME") == ["$HOME"]
    assert parseCommandLineArguments('"тест"') == ["тест"]
    assert parseCommandLineArguments("\"quote'\\\"value\"") == ["quote'\"value"]
    # Adjacent quoted/unquoted tokens concatenate under POSIX shlex
    assert parseCommandLineArguments('"a"b') == ["ab"]
    assert parseCommandLineArguments("") == []
    assert parseCommandLineArguments("   ") == []


def test_parse_rejects_unclosed_quote():
    from utils.run import parseCommandLineArguments

    with pytest.raises(Exception, match="quotation|quote"):
        parseCommandLineArguments('"unterminated')


def test_redirected_run_returns_argv_list_shell_false(tmp_path):
    from utils.run import getCwdCmdEnv
    from utils.runparams import RUN

    script = str(tmp_path / "app.py")
    params = _params(
        arguments='"hello world" "" "*.py" $HOME "тест" "quote\'\\"value"',
        redirected=True,
        useInherited=True,
    )
    cmd, env, use_shell = getCwdCmdEnv(RUN, script, params, tcpServerPort=4321, procuuid="u-1")
    assert use_shell is False
    assert isinstance(cmd, list)
    assert cmd[0] == sys.executable
    dash = cmd.index("--")
    assert cmd[dash:] == [
        "--",
        script,
        "hello world",
        "",
        "*.py",
        "$HOME",
        "тест",
        "quote'\"value",
    ]
    assert not any(k.startswith("CDM_ARG") for k in env)


def test_redirected_profile_outfile_is_argv_element(tmp_path, monkeypatch):
    from utils import run as run_mod
    from utils.runparams import PROFILE

    outfile = str(tmp_path / "out.profile")
    gd = MagicMock()
    gd.getProfileOutputPath.return_value = outfile
    monkeypatch.setattr(run_mod, "GlobalData", lambda: gd, raising=False)

    # buildArgvToProfile imports GlobalData inside the function
    import utils.globals as globals_mod

    monkeypatch.setattr(globals_mod, "GlobalData", lambda: gd)

    script = str(tmp_path / "app.py")
    params = _params(arguments='"a b"', redirected=True)
    cmd, env, use_shell = run_mod.getCwdCmdEnv(
        PROFILE, script, params, tcpServerPort=9, procuuid="p1"
    )
    assert use_shell is False
    assert isinstance(cmd, list)
    assert "--outfile" in cmd
    assert cmd[cmd.index("--outfile") + 1] == outfile
    assert cmd[cmd.index("--") :] == ["--", script, "a b"]
    assert not any(k.startswith("CDM_ARG") for k in env)


def test_custom_terminal_uses_shell_string_with_quoted_args(tmp_path):
    from utils.run import getCwdCmdEnv
    from utils.runparams import RUN

    script = str(tmp_path / "app.py")
    params = _params(
        arguments='"hello world"',
        redirected=False,
        customTerminal="xterm -e ${prog}",
    )
    cmd, env, use_shell = getCwdCmdEnv(RUN, script, params)
    assert use_shell is True
    assert isinstance(cmd, str)
    assert "hello world" in cmd or "hello\\ world" in cmd or "'hello world'" in cmd
    assert "${CDM_ARG" not in cmd
    assert not any(k.startswith("CDM_ARG") for k in env)


def test_runmanager_popen_uses_shell_flag_from_spec(monkeypatch, tmp_path):
    """RemoteProcessWrapper must pass use_shell through to Popen (D03)."""
    import utils.runmanager as rm

    captured = {}

    class FakePopen:
        def __init__(self, cmd, shell=False, cwd=None, env=None):
            captured["cmd"] = cmd
            captured["shell"] = shell
            captured["cwd"] = cwd
            self.returncode = None

        def poll(self):
            return None

        def kill(self):
            return None

        def wait(self):
            return 0

    monkeypatch.setattr(rm, "Popen", FakePopen)
    monkeypatch.setattr(
        rm,
        "getRunParameters",
        lambda _path: _params(arguments='"x y"', redirected=True),
    )
    monkeypatch.setattr(
        rm,
        "getCwdCmdEnv",
        lambda *a, **k: ([sys.executable, "-c", "pass", "x y"], os.environ.copy(), False),
    )

    wrapper = rm.RemoteProcessWrapper(MagicMock(), str(tmp_path / "s.py"), 1234, True, rm.RUN)
    wrapper.start()
    assert captured["shell"] is False
    assert isinstance(captured["cmd"], list)
    assert captured["cmd"][-1] == "x y"
