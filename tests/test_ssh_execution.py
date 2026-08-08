# -*- coding: utf-8 -*-
"""R124: SSHExecutionTarget contract tests with mocked transport."""

from __future__ import annotations

import pytest
from core.execution import ExecutionTarget, assert_execution_target, build_request
from utils.ssh_execution import (
    FakeSSHTransport,
    SSHExecutionTarget,
    SubprocessSSHTransport,
    ssh_cli_available,
    ssh_execution_target,
)


def test_ssh_target_is_execution_target():
    transport = FakeSSHTransport()
    target = SSHExecutionTarget(transport, python="/usr/bin/python3", host_label="box")
    assert isinstance(target, ExecutionTarget)
    assert assert_execution_target(target) is target
    assert target.which_python() == "ssh:box:/usr/bin/python3"
    assert ssh_execution_target(transport) is not None


def test_ssh_run_prepare_does_not_touch_transport():
    transport = FakeSSHTransport(stdout="should-not-run")
    target = SSHExecutionTarget(transport, host_label="dev")
    result = target.run(build_request("/remote/app.py", ["--flag"]))
    assert result.exit_code is None
    assert list(result.argv) == ["python3", "/remote/app.py", "--flag"]
    assert transport.calls == []
    assert result.metadata["backend"] == "ssh"
    assert result.metadata["sync"] == "remote-path-assumed"


def test_ssh_run_wait_uses_transport():
    transport = FakeSSHTransport(exit_code=0, stdout="hello-ssh\n")
    target = SSHExecutionTarget(transport, python="python3", host_label="dev")
    result = target.run(
        build_request("/remote/app.py", ["a"], cwd="/remote/proj", env={"A": "1"}),
        wait=True,
    )
    assert result.exit_code == 0
    assert "hello-ssh" in result.stdout
    assert len(transport.calls) == 1
    argv, cwd, env = transport.calls[0]
    assert argv == ("python3", "/remote/app.py", "a")
    assert cwd == "/remote/proj"
    assert env == {"A": "1"}


def test_ssh_debug_and_profile_argv():
    transport = FakeSSHTransport()
    target = SSHExecutionTarget(transport)
    dbg = target.debug(build_request("/r/x.py"))
    assert dbg.argv[:3] == ("python3", "-m", "pdb")
    prof = target.profile(build_request("/r/x.py", profile_outfile="/r/out.prof"))
    assert "cProfile" in prof.argv
    assert "/r/out.prof" in prof.argv


def test_subprocess_ssh_transport_builds_argv():
    transport = SubprocessSSHTransport(
        "example.com",
        user="alice",
        port=2222,
        identity_file="/tmp/id_test",
        extra_ssh_args=("-o", "BatchMode=yes"),
    )
    assert transport.destination == "alice@example.com"
    argv = transport.build_ssh_argv("python3 /r/a.py")
    assert argv[0] == "ssh"
    assert "-p" in argv and "2222" in argv
    assert "-i" in argv and "/tmp/id_test" in argv
    assert "BatchMode=yes" in argv
    assert argv[-3:] == ["alice@example.com", "--", "python3 /r/a.py"]


def test_subprocess_ssh_transport_rejects_empty_host():
    with pytest.raises(ValueError, match="host"):
        SubprocessSSHTransport("  ")


def test_ssh_cli_available_is_bool():
    assert isinstance(ssh_cli_available(), bool)
