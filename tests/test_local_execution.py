# -*- coding: utf-8 -*-
"""R122: LocalExecutionTarget adapts utils.run to ExecutionTarget."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import parsers  # noqa: E402,F401
import pytest
from core.execution import ExecutionTarget, assert_execution_target, build_request

# Same stub hygiene as test_run_argv — LocalExecutionTarget imports utils.run.
_CODIM = Path(__file__).resolve().parents[1] / "codimension"


def _under_codimension(mod: object) -> bool:
    path = getattr(mod, "__file__", None)
    if path:
        return "/codimension/" in os.path.abspath(path).replace("\\", "/")
    pkg_path = getattr(mod, "__path__", None)
    if not pkg_path:
        return False
    try:
        first = os.path.abspath(list(pkg_path)[0]).replace("\\", "/")
    except Exception:
        return False
    return "/codimension/" in first


@pytest.fixture(autouse=True)
def _purge_stubs():
    import importlib

    dirty = False
    for name in list(sys.modules):
        if name not in ("ui", "utils") and not name.startswith(("ui.", "utils.")):
            continue
        mod = sys.modules[name]
        if _under_codimension(mod):
            if name == "ui.qt" and not hasattr(mod, "QDir"):
                del sys.modules[name]
                dirty = True
            continue
        del sys.modules[name]
        dirty = True
    if dirty:
        importlib.invalidate_caches()
        if str(_CODIM) not in sys.path:
            sys.path.insert(0, str(_CODIM))
    yield


def _params(**overrides):
    from utils.runparams import RunParameters

    p = RunParameters()
    for key, value in overrides.items():
        p[key] = value
    return p


def test_local_target_is_execution_target():
    from utils.local_execution import LocalExecutionTarget

    target = LocalExecutionTarget(_params(redirected=False, useInherited=True))
    assert isinstance(target, ExecutionTarget)
    assert assert_execution_target(target) is target
    assert target.which_python() == sys.executable


def test_local_run_argv_matches_build_argv():
    from utils.local_execution import LocalExecutionTarget
    from utils.run import buildArgvToRun

    params = _params(redirected=False, useInherited=True)
    script = "/tmp/demo.py"
    args = ["--x", "1"]
    expected = buildArgvToRun(script, args, params)
    result = LocalExecutionTarget(params).run(build_request(script, args))
    assert result.exit_code is None
    assert list(result.argv) == expected
    assert result.metadata["backend"] == "local"
    assert result.metadata["mode"] == "run"


def test_local_forced_python():
    from utils.local_execution import LocalExecutionTarget

    target = LocalExecutionTarget(_params(redirected=False), python="/opt/custom/bin/python")
    assert target.which_python() == "/opt/custom/bin/python"
    result = target.run(build_request("s.py"))
    assert result.argv[0] == "/opt/custom/bin/python"


def test_get_cwd_cmd_env_uses_local_target(monkeypatch, tmp_path):
    """getCwdCmdEnv prepares argv through LocalExecutionTarget (R122)."""
    from utils import run as run_mod
    from utils.local_execution import LocalExecutionTarget
    from utils.runparams import RUN

    script = tmp_path / "a.py"
    script.write_text("print(1)\n", encoding="utf-8")
    path = str(script)

    calls: list[str] = []

    class SpyTarget(LocalExecutionTarget):
        def run(self, request, *, wait=False):
            calls.append("run")
            return super().run(request, wait=wait)

    import utils.local_execution as le

    monkeypatch.setattr(le, "LocalExecutionTarget", SpyTarget)

    params = _params(redirected=True, useInherited=True, arguments="a b")
    argv, _env, use_shell = run_mod.getCwdCmdEnv(RUN, path, params, 9, "uuid-1")
    assert use_shell is False
    assert argv[0] == sys.executable
    assert path in argv
    assert "a" in argv and "b" in argv
    assert calls == ["run"]


def test_local_wait_executes_subprocess(tmp_path: Path):
    script = tmp_path / "hello.py"
    script.write_text("print('hi')\n", encoding="utf-8")
    from utils.local_execution import LocalExecutionTarget

    result = LocalExecutionTarget(_params(redirected=False, useInherited=True)).run(
        build_request(str(script)),
        wait=True,
    )
    assert result.exit_code == 0
    assert "hi" in result.stdout
