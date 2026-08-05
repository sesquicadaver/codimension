# -*- coding: utf-8 -*-
"""D03/E01/E02: redirected argv + custom-terminal launcher / profile."""

from __future__ import annotations

import importlib
import json
import os
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Ensure package-relative parsers provide cdmpyparser before utils.run import.
import parsers  # noqa: E402,F401
import pytest

_CODIM = Path(__file__).resolve().parents[1] / "codimension"


def _under_codimension(mod: object) -> bool:
    """True if module resolves under the repo ``codimension/`` tree."""
    path = getattr(mod, "__file__", None)
    if path:
        return "/codimension/" in os.path.abspath(path).replace("\\", "/")
    pkg_path = getattr(mod, "__path__", None)
    if pkg_path is None:
        return False
    try:
        first = os.path.abspath(list(pkg_path)[0]).replace("\\", "/")
    except Exception:
        return False
    return "/codimension/" in first


def _purge_collection_stubs() -> None:
    """Drop incomplete ``ui`` / ``utils`` stubs left by other suites (CI order).

    ``utils.run`` imports ``encoding`` → ``settings`` → ``ui.qt``, so stubs for
    any of those break a real import (audit D03 CI).
    """
    dirty = False
    for name in list(sys.modules):
        if name not in ("ui", "utils") and not name.startswith(("ui.", "utils.")):
            continue
        mod = sys.modules[name]
        if _under_codimension(mod):
            if name == "utils.run" and not hasattr(mod, "getCwdCmdEnv"):
                del sys.modules[name]
                dirty = True
            elif name == "ui.qt" and not hasattr(mod, "QDir"):
                del sys.modules[name]
                dirty = True
            continue
        del sys.modules[name]
        dirty = True
    if dirty:
        importlib.invalidate_caches()
        if str(_CODIM) not in sys.path:
            sys.path.insert(0, str(_CODIM))
        import parsers as _parsers  # noqa: F401


@pytest.fixture(autouse=True)
def _real_utils_run():
    """Restore real run/settings/qt modules before each test in this module."""
    _purge_collection_stubs()
    yield


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
    assert parseCommandLineArguments('"quote\'\\"value"') == ["quote'\"value"]
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
    cmd, env, use_shell = run_mod.getCwdCmdEnv(PROFILE, script, params, tcpServerPort=9, procuuid="p1")
    assert use_shell is False
    assert isinstance(cmd, list)
    assert "--outfile" in cmd
    assert cmd[cmd.index("--outfile") + 1] == outfile
    assert cmd[cmd.index("--") :] == ["--", script, "a b"]
    assert not any(k.startswith("CDM_ARG") for k in env)


def test_custom_terminal_embeds_launcher_not_argv(tmp_path):
    """E01: ${prog} is one launcher path; user argv must not enter the template."""
    from utils.run import getCwdCmdEnv
    from utils.runparams import RUN

    script = str(tmp_path / "app.py")
    params = _params(
        arguments='"hello world" $HOME "$(printf injected)"',
        redirected=False,
        customTerminal='/bin/bash -c "${prog}"',
    )
    cmd, env, use_shell = getCwdCmdEnv(RUN, script, params)
    assert use_shell is True
    assert isinstance(cmd, str)
    assert "${prog}" not in cmd
    assert "hello world" not in cmd
    assert "$HOME" not in cmd
    assert "printf injected" not in cmd
    assert "launch.py" in cmd
    assert not any(k.startswith("CDM_ARG") for k in env)


def test_custom_terminal_recommended_template_preserves_argv(tmp_path):
    """E01: execute recommended bash -c \"${prog}\" and compare sys.argv."""
    import json
    import subprocess

    from utils.run import getCwdCmdEnv
    from utils.runparams import RUN

    out_file = tmp_path / "argv.json"
    script = tmp_path / "dump_argv.py"
    script.write_text(
        f"import json, sys\njson.dump(sys.argv[1:], open({str(out_file)!r}, 'w', encoding='utf-8'))\n",
        encoding="utf-8",
    )
    args = '"a b" "" "$HOME" "$(printf injected)" "quote\'\\"value" "тест"'
    params = _params(
        arguments=args,
        redirected=False,
        customTerminal='/bin/bash -c "${prog}"',
        useInherited=True,
    )
    cmd, env, use_shell = getCwdCmdEnv(RUN, str(script), params)
    assert use_shell is True
    match = re.search(r"(/tmp/cdm-run-[A-Za-z0-9_./+-]+/launch\.py)", cmd)
    assert match, cmd
    launch_dir = Path(match.group(1)).parent
    completed = subprocess.run(cmd, shell=True, env=env, cwd=str(tmp_path), check=False)
    assert completed.returncode == 0
    got = json.loads(out_file.read_text(encoding="utf-8"))
    assert got == ["a b", "", "$HOME", "$(printf injected)", "quote'\"value", "тест"]
    # E04: launcher must remove argv.json / launch.py / work dir before execvp
    assert not launch_dir.exists()


def test_launcher_cleans_temp_dir_before_execvp(tmp_path):
    """E04: after a successful launch, the cdm-run work directory is gone."""
    import subprocess

    from utils.run import writeArgvLauncher

    marker = tmp_path / "ran.txt"
    target = tmp_path / "target.py"
    target.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ok', encoding='utf-8')\n",
        encoding="utf-8",
    )
    launch = writeArgvLauncher([sys.executable, str(target)])
    work = Path(launch).parent
    assert (work / "argv.json").is_file()
    completed = subprocess.run([launch], check=False)
    assert completed.returncode == 0
    assert marker.read_text(encoding="utf-8") == "ok"
    assert not work.exists()


def test_cleanup_stale_argv_launchers(tmp_path, monkeypatch):
    """E04: opportunistic cleanup removes aged cdm-run-* directories."""
    import time

    from utils import run as run_mod

    monkeypatch.setattr(run_mod.tempfile, "gettempdir", lambda: str(tmp_path))
    stale = tmp_path / "cdm-run-stale"
    stale.mkdir()
    (stale / "argv.json").write_text('["x"]', encoding="utf-8")
    old = time.time() - 90000
    os.utime(stale, (old, old))
    fresh = tmp_path / "cdm-run-fresh"
    fresh.mkdir()
    (fresh / "argv.json").write_text('["y"]', encoding="utf-8")
    assert run_mod.cleanupStaleArgvLaunchers(max_age_seconds=86400) == 1
    assert not stale.exists()
    assert fresh.exists()


def test_custom_terminal_profile_uses_cprofile(tmp_path, monkeypatch):
    """E02: non-redirected Profile must not fall back to bare Run argv."""
    from utils import run as run_mod
    from utils.runparams import PROFILE

    outfile = str(tmp_path / "out.profile")
    gd = MagicMock()
    gd.getProfileOutputPath.return_value = outfile
    import utils.globals as globals_mod

    monkeypatch.setattr(globals_mod, "GlobalData", lambda: gd)

    script = str(tmp_path / "app.py")
    Path(script).write_text("x = 1\n", encoding="utf-8")
    params = _params(
        arguments='"a b"',
        redirected=False,
        customTerminal='/bin/bash -c "${prog}"',
    )
    cmd, _env, use_shell = run_mod.getCwdCmdEnv(PROFILE, script, params, procuuid="p2")
    assert use_shell is True
    match = re.search(r"(/tmp/cdm-run-[A-Za-z0-9_./+-]+/launch\.py)", cmd)
    assert match, cmd
    launch_path = match.group(1)
    argv = json.loads(Path(launch_path).with_name("argv.json").read_text(encoding="utf-8"))
    assert argv[1:4] == ["-m", "cProfile", "-o"]
    assert argv[4] == outfile
    assert argv[5] == script
    assert argv[6] == "a b"
    # E05: profile launcher embeds completion marker (subprocess path, not execvp)
    launch_src = Path(launch_path).read_text(encoding="utf-8")
    assert "subprocess.call" in launch_src
    assert outfile + ".done" in launch_src or run_mod.getProfileCompletionMarkerPath(outfile) in launch_src


def test_custom_terminal_profile_allows_background_template(tmp_path, monkeypatch):
    """E05: trailing '&' is not a hard refuse; completion is marker-gated."""
    from utils import run as run_mod
    from utils.runparams import PROFILE

    gd = MagicMock()
    gd.getProfileOutputPath.return_value = str(tmp_path / "o.prof")
    import utils.globals as globals_mod

    monkeypatch.setattr(globals_mod, "GlobalData", lambda: gd)

    params = _params(
        redirected=False,
        customTerminal='xterm -e /bin/bash -c "${prog}" &',
    )
    cmd, _env, use_shell = run_mod.getCwdCmdEnv(PROFILE, str(tmp_path / "a.py"), params, procuuid="p3")
    assert use_shell is True
    assert "launch.py" in cmd


def test_profile_launcher_writes_marker_after_child(tmp_path):
    """E05: completion marker appears only after the profiled argv exits."""
    import subprocess

    from utils.run import getProfileCompletionMarkerPath, writeArgvLauncher

    outfile = tmp_path / "out.profile"
    marker = Path(getProfileCompletionMarkerPath(str(outfile)))
    # Simulate cProfile -o by writing a non-empty outfile then exiting.
    target = tmp_path / "write_profile.py"
    target.write_text(
        f"from pathlib import Path\nPath({str(outfile)!r}).write_bytes(b'prof')\n",
        encoding="utf-8",
    )
    launch = writeArgvLauncher([sys.executable, str(target)], completion_marker=str(marker))
    work = Path(launch).parent
    assert not marker.exists()
    completed = subprocess.run([launch], check=False)
    assert completed.returncode == 0
    assert marker.is_file()
    assert outfile.read_bytes() == b"prof"
    assert not work.exists()


def test_profile_results_ready_requires_nonempty_outfile(tmp_path):
    from utils.run import getProfileCompletionMarkerPath, profileResultsReady

    outfile = tmp_path / "o.prof"
    marker = Path(getProfileCompletionMarkerPath(str(outfile)))
    marker.write_text("done\n", encoding="utf-8")
    assert profileResultsReady(str(outfile), str(marker)) is False
    outfile.write_bytes(b"x")
    assert profileResultsReady(str(outfile), str(marker)) is True


def test_wait_timer_emits_profile_once_while_shell_alive(monkeypatch, tmp_path):
    """E05: results emit on marker readiness even if Popen has not exited."""
    import utils.runmanager as rm
    from utils.run import profileResultsReady as _ready

    outfile = tmp_path / "sess.profile.out"
    marker = Path(str(outfile) + ".done")
    outfile.write_bytes(b"stats")
    marker.write_text("done\n", encoding="utf-8")

    gd = MagicMock()
    gd.getProfileOutputPath.return_value = str(outfile)
    monkeypatch.setattr(rm, "GlobalData", lambda: gd)

    class FakeProc:
        def poll(self):
            return None

        def wait(self):
            return 0

    manager = rm.RunManager.__new__(rm.RunManager)
    manager._RunManager__waitTimer = MagicMock()
    manager.sigProfilingResults = MagicMock()

    wrapper = rm.RemoteProcessWrapper.__new__(rm.RemoteProcessWrapper)
    wrapper.redirected = False
    wrapper.kind = rm.PROFILE
    wrapper.path = str(tmp_path / "s.py")
    wrapper.procuuid = "u-e05"
    wrapper.startTime = __import__("datetime").datetime.now()
    wrapper.finishTime = None
    wrapper.profileOutfile = str(outfile)
    wrapper.profileCompletionMarker = str(marker)
    wrapper.profileResultsSent = False
    wrapper.profileWaitDeadline = None
    wrapper._RemoteProcessWrapper__proc = FakeProc()
    wrapper.profileResultsReady = lambda: _ready(wrapper.profileOutfile, wrapper.profileCompletionMarker)

    class Item:
        kind = rm.PROFILE

        def __init__(self):
            self.procWrapper = wrapper

    manager._RunManager__processes = [Item()]
    rm.RunManager._RunManager__onWaitTimer(manager)
    assert manager.sigProfilingResults.emit.call_count == 1
    assert wrapper.profileResultsSent is True
    rm.RunManager._RunManager__onWaitTimer(manager)
    assert manager.sigProfilingResults.emit.call_count == 1
    assert len(manager._RunManager__processes) == 1


def test_wait_timer_timeout_after_shell_death_no_emit(monkeypatch, tmp_path):
    """E05 test-spec #7: after shell exit, timeout drops without success emit."""
    import utils.runmanager as rm
    from utils.run import PROFILE_COMPLETION_TIMEOUT_SEC, profileResultsReady as _ready

    outfile = tmp_path / "late.profile.out"
    marker = Path(str(outfile) + ".done")
    # No marker / no outfile → never ready
    assert _ready(str(outfile), str(marker)) is False

    monkeypatch.setattr(rm, "GlobalData", lambda: MagicMock())

    class DeadProc:
        def poll(self):
            return 0

        def wait(self):
            return 0

    manager = rm.RunManager.__new__(rm.RunManager)
    manager._RunManager__waitTimer = MagicMock()
    manager.sigProfilingResults = MagicMock()

    wrapper = rm.RemoteProcessWrapper.__new__(rm.RemoteProcessWrapper)
    wrapper.redirected = False
    wrapper.kind = rm.PROFILE
    wrapper.path = str(tmp_path / "s.py")
    wrapper.procuuid = "u-timeout"
    wrapper.startTime = __import__("datetime").datetime.now()
    wrapper.finishTime = None
    wrapper.profileOutfile = str(outfile)
    wrapper.profileCompletionMarker = str(marker)
    wrapper.profileResultsSent = False
    wrapper.profileWaitDeadline = None
    wrapper.profileShellBackgrounded = False
    wrapper._RemoteProcessWrapper__proc = DeadProc()
    wrapper.profileResultsReady = lambda: _ready(wrapper.profileOutfile, wrapper.profileCompletionMarker)

    class Item:
        kind = rm.PROFILE

        def __init__(self):
            self.procWrapper = wrapper

    manager._RunManager__processes = [Item()]
    # First tick after shell death: set deadline, keep process, no emit
    rm.RunManager._RunManager__onWaitTimer(manager)
    assert manager.sigProfilingResults.emit.call_count == 0
    assert len(manager._RunManager__processes) == 1
    assert wrapper.profileWaitDeadline is not None

    # Force timeout
    wrapper.profileWaitDeadline = __import__("time").time() - 1
    assert PROFILE_COMPLETION_TIMEOUT_SEC == 60
    rm.RunManager._RunManager__onWaitTimer(manager)
    assert manager.sigProfilingResults.emit.call_count == 0
    assert manager._RunManager__processes == []


def test_wait_timer_no_emit_on_empty_outfile(monkeypatch, tmp_path):
    """E05: marker alone with empty outfile must not emit."""
    import utils.runmanager as rm
    from utils.run import profileResultsReady as _ready

    outfile = tmp_path / "empty.profile.out"
    marker = Path(str(outfile) + ".done")
    outfile.write_bytes(b"")
    marker.write_text("done\n", encoding="utf-8")
    assert _ready(str(outfile), str(marker)) is False

    monkeypatch.setattr(rm, "GlobalData", lambda: MagicMock())

    manager = rm.RunManager.__new__(rm.RunManager)
    manager._RunManager__waitTimer = MagicMock()
    manager.sigProfilingResults = MagicMock()

    wrapper = rm.RemoteProcessWrapper.__new__(rm.RemoteProcessWrapper)
    wrapper.redirected = False
    wrapper.kind = rm.PROFILE
    wrapper.path = str(tmp_path / "s.py")
    wrapper.procuuid = "u-empty"
    wrapper.startTime = __import__("datetime").datetime.now()
    wrapper.finishTime = None
    wrapper.profileOutfile = str(outfile)
    wrapper.profileCompletionMarker = str(marker)
    wrapper.profileResultsSent = False
    wrapper.profileWaitDeadline = None
    wrapper._RemoteProcessWrapper__proc = MagicMock(poll=lambda: None, wait=lambda: 0)
    wrapper.profileResultsReady = lambda: _ready(wrapper.profileOutfile, wrapper.profileCompletionMarker)

    class Item:
        kind = rm.PROFILE

        def __init__(self):
            self.procWrapper = wrapper

    manager._RunManager__processes = [Item()]
    rm.RunManager._RunManager__onWaitTimer(manager)
    assert manager.sigProfilingResults.emit.call_count == 0
    assert wrapper.profileResultsSent is False


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
