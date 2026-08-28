# -*- coding: utf-8 -*-
"""R123: DockerExecutionTarget — argv contract + docker-or-skip integration."""

from __future__ import annotations

from pathlib import Path

import pytest
from core.execution import ExecutionTarget, assert_execution_target, build_request
from utils.docker_execution import (
    DockerExecutionTarget,
    docker_available,
    docker_execution_target,
)


def test_docker_target_is_execution_target(tmp_path: Path):
    target = DockerExecutionTarget(str(tmp_path), image="python:3.12-slim")
    assert isinstance(target, ExecutionTarget)
    assert assert_execution_target(target) is target
    assert target.which_python() == "docker:python:3.12-slim:python"
    assert docker_execution_target(str(tmp_path)) is not None


def test_docker_run_argv_mounts_workspace(tmp_path: Path):
    script = tmp_path / "hello.py"
    script.write_text("print(1)\n", encoding="utf-8")
    target = DockerExecutionTarget(str(tmp_path), image="python:3.11-slim", python="python3")
    plan = target.prepare_run(build_request(str(script), ["--x"]))
    argv = list(plan.argv)
    assert argv[0] == "docker"
    assert "run" in argv
    assert "--rm" in argv
    mount = f"{tmp_path.resolve()}:/workspace"
    assert mount in argv
    assert "-w" in argv
    assert argv[argv.index("-w") + 1] == "/workspace"
    assert argv[-3:] == ["python3", "/workspace/hello.py", "--x"]
    assert plan.metadata["backend"] == "docker"
    assert plan.metadata["image"] == "python:3.11-slim"


def test_docker_rejects_script_outside_workspace(tmp_path: Path):
    target = DockerExecutionTarget(str(tmp_path))
    with pytest.raises(ValueError, match="outside workspace"):
        target.prepare_run(build_request("/tmp/not-in-workspace.py"))


def test_docker_maps_nested_script(tmp_path: Path):
    nested = tmp_path / "pkg"
    nested.mkdir()
    script = nested / "mod.py"
    script.write_text("pass\n", encoding="utf-8")
    target = DockerExecutionTarget(str(tmp_path), container_workdir="/ws")
    assert target.map_to_container(str(script)) == "/ws/pkg/mod.py"


def test_docker_debug_and_profile_argv(tmp_path: Path):
    script = tmp_path / "app.py"
    script.write_text("x=1\n", encoding="utf-8")
    target = DockerExecutionTarget(str(tmp_path))
    dbg = target.prepare_debug(build_request(str(script)))
    assert "-m" in dbg.argv and "pdb" in dbg.argv
    assert dbg.metadata["mode"] == "debug"

    prof = target.prepare_profile(build_request(str(script), profile_outfile=str(tmp_path / "out.prof")))
    assert "cProfile" in prof.argv
    assert "/workspace/out.prof" in prof.argv
    assert prof.metadata["mode"] == "profile"


def test_docker_env_and_extra_run_args(tmp_path: Path):
    script = tmp_path / "a.py"
    script.write_text("pass\n", encoding="utf-8")
    target = DockerExecutionTarget(
        str(tmp_path),
        extra_run_args=("--network=none",),
    )
    plan = target.prepare_run(build_request(str(script), env={"FOO": "bar"}))
    argv = list(plan.argv)
    assert "-e" in argv
    assert "FOO=bar" in argv
    assert "--network=none" in argv


@pytest.mark.skipif(not docker_available(), reason="docker CLI/daemon not available")
def test_docker_run_wait_integration():
    """End-to-end: mount workspace and execute a script in python:3.12-slim.

    Use a home-relative workspace (not pytest's mode-700 ``/tmp/pytest-*``):
    snap-confined Docker often mounts those trees as empty.
    """
    import tempfile

    home_base = Path.home() / ".cache" / "codimension-docker-r123"
    home_base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="r123-", dir=str(home_base)) as raw:
        workspace = Path(raw)
        workspace.chmod(0o755)
        script = workspace / "hello.py"
        script.write_text("print('docker-r123')\n", encoding="utf-8")
        target = DockerExecutionTarget(str(workspace), image="python:3.12-slim")
        result = target.run(build_request(str(script)))
        assert result.exit_code == 0, result.stderr
        assert "docker-r123" in result.stdout
        assert result.metadata["backend"] == "docker"
