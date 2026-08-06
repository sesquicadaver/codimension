# -*- coding: utf-8 -*-
"""R121: ExecutionTarget protocol + fake target contract tests."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import pytest
from core.execution import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionTarget,
    assert_execution_target,
    build_request,
)

Mode = Literal["run", "debug", "profile"]


@dataclass
class FakeExecutionTarget:
    """Recording stand-in used to prove the protocol surface (R121)."""

    python: str = "/fake/bin/python"
    calls: list[tuple[Mode, ExecutionRequest]] = field(default_factory=list)
    exit_code: int = 0

    def which_python(self) -> str:
        return self.python

    def run(self, request: ExecutionRequest) -> ExecutionResult:
        return self._record("run", request)

    def debug(self, request: ExecutionRequest) -> ExecutionResult:
        return self._record("debug", request)

    def profile(self, request: ExecutionRequest) -> ExecutionResult:
        return self._record("profile", request)

    def _record(self, mode: Mode, request: ExecutionRequest) -> ExecutionResult:
        self.calls.append((mode, request))
        argv = [self.python, f"--mode={mode}", request.script, *request.args]
        if mode == "profile" and request.profile_outfile:
            argv.extend(["--outfile", request.profile_outfile])
        if mode == "debug" and request.tcp_port is not None:
            argv.extend(["--port", str(request.tcp_port)])
        return ExecutionResult(
            exit_code=self.exit_code,
            argv=tuple(argv),
            metadata={"mode": mode},
        )


def test_fake_target_satisfies_runtime_checkable_protocol() -> None:
    """isinstance(…, ExecutionTarget) holds for a structural fake."""
    target = FakeExecutionTarget()
    assert isinstance(target, ExecutionTarget)
    assert assert_execution_target(target) is target


def test_fake_target_which_python_and_modes() -> None:
    """run / debug / profile record requests and return argv via which_python."""
    target = FakeExecutionTarget(python="/opt/proj/.venv/bin/python")
    assert target.which_python() == "/opt/proj/.venv/bin/python"

    req = build_request("app.py", ["--flag"], cwd="/tmp/proj", procuuid="u1")
    run_res = target.run(req)
    assert run_res.exit_code == 0
    assert run_res.argv[0] == target.which_python()
    assert run_res.argv[1] == "--mode=run"
    assert "app.py" in run_res.argv

    dbg = target.debug(build_request("app.py", tcp_port=4242, procuuid="u2"))
    assert "--port" in dbg.argv and "4242" in dbg.argv

    prof = target.profile(build_request("app.py", profile_outfile="/tmp/out.prof"))
    assert "--outfile" in prof.argv and "/tmp/out.prof" in prof.argv

    assert [mode for mode, _ in target.calls] == ["run", "debug", "profile"]


def test_assert_execution_target_rejects_incomplete() -> None:
    """Objects missing protocol methods fail the assertion helper."""

    class _NotATarget:
        def which_python(self) -> str:
            return "x"

    with pytest.raises(TypeError, match="ExecutionTarget"):
        assert_execution_target(_NotATarget())


def test_execution_request_normalizes_args() -> None:
    """args sequences become tuples on the frozen request."""
    req = ExecutionRequest(script="s.py", args=["a", "b"])  # type: ignore[arg-type]
    assert req.args == ("a", "b")


def test_core_execution_import_subprocess_without_qt() -> None:
    """Gate: importing core.execution must not pull Qt."""
    root = Path(__file__).resolve().parents[1]
    code = (
        "import sys\n"
        f"sys.path.insert(0, {str(root / 'codimension')!r})\n"
        f"sys.path.insert(0, {str(root)!r})\n"
        "assert 'PyQt5' not in sys.modules\n"
        "from core.execution import ExecutionTarget, ExecutionRequest\n"
        "assert 'PyQt5' not in sys.modules\n"
        "print('ok')\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)
    assert "ok" in proc.stdout
