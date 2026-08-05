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
    match = re.search(r"(/[A-Za-z0-9._/=+-]+/cdm-run-[A-Za-z0-9_./+-]+/launch\.py)", cmd)
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

    root = tmp_path / "cdm-run"
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    monkeypatch.setattr(run_mod, "_launcherWorkRoots", lambda: [str(root)])
    monkeypatch.setattr(run_mod, "_legacyTmpCleanupMarkerPath", lambda: str(tmp_path / "legacy.done"))
    monkeypatch.setattr(run_mod.tempfile, "gettempdir", lambda: str(tmp_path / "noscan"))
    (tmp_path / "noscan").mkdir()
    stale = root / "cdm-run-stale"
    stale.mkdir(mode=0o700)
    os.chmod(stale, 0o700)
    (stale / "argv.json").write_text('["x"]', encoding="utf-8")
    old = time.time() - 90000
    os.utime(stale, (old, old))
    fresh = root / "cdm-run-fresh"
    fresh.mkdir(mode=0o700)
    os.chmod(fresh, 0o700)
    (fresh / "argv.json").write_text('["y"]', encoding="utf-8")
    assert run_mod.cleanupStaleArgvLaunchers(max_age_seconds=86400) == 1
    assert not stale.exists()
    assert fresh.exists()


def test_cleanup_refuses_symlink_cdm_run_dir(tmp_path, monkeypatch):
    """F07: symlink named cdm-run-* must not delete the target's files."""
    import time

    from utils import run as run_mod

    root = tmp_path / "scan-root"
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    victim = tmp_path / "victim"
    victim.mkdir(mode=0o700)
    os.chmod(victim, 0o700)
    secret = victim / "secret.txt"
    secret.write_text("keep-me", encoding="utf-8")
    link = root / "cdm-run-evil"
    link.symlink_to(victim, target_is_directory=True)
    old = time.time() - 90000
    os.utime(victim, (old, old), follow_symlinks=False)
    monkeypatch.setattr(run_mod, "_launcherWorkRoots", lambda: [str(root)])
    monkeypatch.setattr(run_mod, "_legacyTmpCleanupMarkerPath", lambda: str(tmp_path / "legacy.done"))
    assert run_mod.cleanupStaleArgvLaunchers(max_age_seconds=86400) == 0
    assert secret.read_text(encoding="utf-8") == "keep-me"
    assert link.is_symlink()


def test_cleanup_legacy_tmp_runs_only_once(tmp_path, monkeypatch):
    """F07: global tempdir is scanned at most once (legacy migration marker)."""
    import time

    from utils import run as run_mod

    trusted = tmp_path / "trusted"
    trusted.mkdir(mode=0o700)
    os.chmod(trusted, 0o700)
    tmp = tmp_path / "systmp"
    tmp.mkdir(mode=0o700)
    os.chmod(tmp, 0o700)
    marker = tmp_path / "legacy.done"
    legacy = tmp / "cdm-run-legacy"
    legacy.mkdir(mode=0o700)
    os.chmod(legacy, 0o700)
    (legacy / "argv.json").write_text('["z"]', encoding="utf-8")
    old = time.time() - 90000
    os.utime(legacy, (old, old))

    monkeypatch.setattr(run_mod, "_launcherWorkRoots", lambda: [str(trusted)])
    monkeypatch.setattr(run_mod, "_legacyTmpCleanupMarkerPath", lambda: str(marker))
    monkeypatch.setattr(run_mod.tempfile, "gettempdir", lambda: str(tmp))

    assert run_mod.cleanupStaleArgvLaunchers(max_age_seconds=86400) == 1
    assert not legacy.exists()
    assert marker.is_file()

    # Recreate aged leftover; second call must not scan system temp again.
    legacy.mkdir(mode=0o700)
    os.chmod(legacy, 0o700)
    (legacy / "argv.json").write_text('["z2"]', encoding="utf-8")
    os.utime(legacy, (old, old))
    assert run_mod.cleanupStaleArgvLaunchers(max_age_seconds=86400) == 0
    assert legacy.exists()


def test_launcher_uses_absolute_interpreter_shebang_and_settings_root(tmp_path, monkeypatch):
    """E06: shebang is sys.executable; work dir prefers settings-like root."""
    from utils import run as run_mod

    root = tmp_path / "cdm-run"
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    monkeypatch.setattr(run_mod, "_launcherWorkRoots", lambda: [str(root)])
    assert run_mod._isTrustedLauncherWorkRoot(str(root)) is True
    assert run_mod._ensureLauncherWorkRoot() == str(root)
    launch = run_mod.writeArgvLauncher([sys.executable, "-c", "pass"])
    launch_path = Path(launch)
    assert str(root) in str(launch_path)
    first = launch_path.read_text(encoding="utf-8").splitlines()[0]
    assert first == f"#!{sys.executable}"
    assert "/usr/bin/env" not in first
    # cleanup leftover for this test process
    for child in launch_path.parent.iterdir():
        child.unlink()
    launch_path.parent.rmdir()


def test_shell_safe_path_allows_spaces_and_unicode(tmp_path):
    """E06: ${prog} embedding allows spaces/Unicode; rejects shell metacharacters."""
    from utils.run import assertShellSafePath, assertShebangInterpreter

    spaced = tmp_path / "my dir" / "launch.py"
    spaced.parent.mkdir()
    spaced.write_text("x", encoding="utf-8")
    assert assertShellSafePath(str(spaced)).endswith("launch.py")

    unicode_dir = tmp_path / "проєкт" / "launch.py"
    unicode_dir.parent.mkdir()
    unicode_dir.write_text("x", encoding="utf-8")
    assert "проєкт" in assertShellSafePath(str(unicode_dir))

    with pytest.raises(RuntimeError, match="not safe"):
        assertShellSafePath(str(tmp_path / 'a$PWD' / "x"))
    with pytest.raises(RuntimeError, match="not safe"):
        assertShellSafePath(str(tmp_path / "a;b" / "x"))
    with pytest.raises(RuntimeError, match="shebang"):
        assertShebangInterpreter(str(tmp_path / "has space" / "python"))


def test_ensure_work_root_skips_noexec(tmp_path, monkeypatch):
    """E06: write-ok root that fails execute probe must be skipped."""
    from utils import run as run_mod

    noexec = tmp_path / "noexec-cdm-run"
    noexec.mkdir(mode=0o700)
    os.chmod(noexec, 0o700)
    good = tmp_path / "exec-cdm-run"
    good.mkdir(mode=0o700)
    os.chmod(good, 0o700)

    def fake_probe(root, _interpreter):
        return os.path.abspath(root) == os.path.abspath(str(good))

    monkeypatch.setattr(run_mod, "_launcherWorkRoots", lambda: [str(noexec), str(good)])
    monkeypatch.setattr(run_mod, "_probeDirectoryAllowsExec", fake_probe)
    assert run_mod._ensureLauncherWorkRoot() == str(good)


def test_ensure_work_root_raises_when_nothing_executable(tmp_path, monkeypatch):
    """E06: if settings/XDG and system temp are noexec, raise clearly."""
    from utils import run as run_mod

    bad = tmp_path / "cdm-run"
    bad.mkdir(mode=0o700)
    os.chmod(bad, 0o700)
    systmp = tmp_path / "systmp"
    systmp.mkdir(mode=0o700)
    os.chmod(systmp, 0o700)
    monkeypatch.setattr(run_mod, "_launcherWorkRoots", lambda: [str(bad)])
    monkeypatch.setattr(run_mod, "_probeDirectoryAllowsExec", lambda *_a, **_k: False)
    monkeypatch.setattr(run_mod.tempfile, "gettempdir", lambda: str(systmp))
    with pytest.raises(RuntimeError, match="no executable work directory"):
        run_mod._ensureLauncherWorkRoot()


def test_launcher_rejects_untrusted_work_root(tmp_path, monkeypatch):
    """E06: world-accessible parent must not be used; fall back to sticky temp."""
    from utils import run as run_mod

    bad = tmp_path / "open-cdm-run"
    bad.mkdir()
    os.chmod(bad, 0o777)
    mode = bad.stat().st_mode & 0o777
    assert mode & 0o077, f"expected world/group bits, got {oct(mode)}"
    assert run_mod._isTrustedLauncherWorkRoot(str(bad)) is False
    monkeypatch.setattr(run_mod, "_launcherWorkRoots", lambda: [str(bad)])
    assert run_mod._ensureLauncherWorkRoot() is None
    launch = Path(run_mod.writeArgvLauncher([sys.executable, "-c", "pass"]))
    assert bad.resolve() not in launch.resolve().parents
    for child in launch.parent.iterdir():
        child.unlink()
    launch.parent.rmdir()


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
    match = re.search(r"(/[A-Za-z0-9._/=+-]+/cdm-run-[A-Za-z0-9_./+-]+/launch\.py)", cmd)
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
    wrapper.profileWaitDeadline = __import__("time").time() + 3600
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
    assert not marker.exists()
    rm.RunManager._RunManager__onWaitTimer(manager)
    assert manager.sigProfilingResults.emit.call_count == 1
    assert len(manager._RunManager__processes) == 1


def test_wait_timer_timeout_uses_start_deadline_not_shell_heuristic(monkeypatch, tmp_path):
    """E05: single start-based deadline; template '&' is irrelevant."""
    import utils.runmanager as rm
    from utils.run import PROFILE_COMPLETION_TIMEOUT_SEC
    from utils.run import profileResultsReady as _ready

    outfile = tmp_path / "late.profile.out"
    marker = Path(str(outfile) + ".done")
    assert _ready(str(outfile), str(marker)) is False
    assert PROFILE_COMPLETION_TIMEOUT_SEC == 3600

    monkeypatch.setattr(rm, "GlobalData", lambda: MagicMock())

    class AliveProc:
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
    wrapper.procuuid = "u-timeout"
    wrapper.startTime = __import__("datetime").datetime.now()
    wrapper.finishTime = None
    wrapper.profileOutfile = str(outfile)
    wrapper.profileCompletionMarker = str(marker)
    wrapper.profileResultsSent = False
    wrapper.profileWaitDeadline = __import__("time").time() - 1
    wrapper._RemoteProcessWrapper__proc = AliveProc()
    wrapper.profileResultsReady = lambda: _ready(wrapper.profileOutfile, wrapper.profileCompletionMarker)

    class Item:
        kind = rm.PROFILE

        def __init__(self):
            self.procWrapper = wrapper

    manager._RunManager__processes = [Item()]
    rm.RunManager._RunManager__onWaitTimer(manager)
    assert manager.sigProfilingResults.emit.call_count == 0
    assert manager._RunManager__processes == []
    assert not marker.exists()


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
