# -*- coding: utf-8 -*-
"""R125: KubernetesExecutionTarget contract tests with mocked transport."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import parsers  # noqa: E402,F401
import pytest

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
            continue
        del sys.modules[name]
        dirty = True
    if dirty:
        importlib.invalidate_caches()
        if str(_CODIM) not in sys.path:
            sys.path.insert(0, str(_CODIM))
    yield


def test_k8s_target_is_execution_target():
    from core.execution import ExecutionTarget, assert_execution_target
    from utils.k8s_execution import FakeK8sJobTransport, KubernetesExecutionTarget, kubernetes_execution_target

    transport = FakeK8sJobTransport()
    target = KubernetesExecutionTarget(transport, python="python3", cluster_label="dev")
    assert isinstance(target, ExecutionTarget)
    assert assert_execution_target(target) is target
    assert target.which_python() == "k8s:dev:python3"
    assert kubernetes_execution_target(transport) is not None


def test_k8s_prepare_run_includes_job_stub():
    from core.execution import build_request
    from utils.k8s_execution import FakeK8sJobTransport, KubernetesExecutionTarget

    transport = FakeK8sJobTransport()
    target = KubernetesExecutionTarget(transport, image="python:3.12-slim")
    plan = target.prepare_run(build_request("/app/main.py", ["--x"]))
    assert list(plan.argv) == ["python", "/app/main.py", "--x"]
    assert transport.calls == []
    stub = json.loads(plan.metadata["job_stub"])
    assert stub["kind"] == "Job"
    assert stub["spec"]["template"]["spec"]["containers"][0]["image"] == "python:3.12-slim"
    assert plan.metadata["sync"] == "in-image-or-volume-assumed"


def test_k8s_run_wait_uses_transport():
    from core.execution import build_request
    from utils.k8s_execution import FakeK8sJobTransport, KubernetesExecutionTarget

    transport = FakeK8sJobTransport(exit_code=0, stdout="k8s-ok\n")
    target = KubernetesExecutionTarget(transport, python="python3")
    result = target.run(
        build_request("/app/main.py", ["a"], cwd="/app", env={"K": "1"}),
    )
    assert result.exit_code == 0
    assert "k8s-ok" in result.stdout
    assert len(transport.calls) == 1
    argv, env, cwd = transport.calls[0]
    assert argv == ("python3", "/app/main.py", "a")
    assert env == {"K": "1"}
    assert cwd == "/app"


def test_k8s_debug_and_profile_argv():
    from core.execution import build_request
    from utils.k8s_execution import FakeK8sJobTransport, KubernetesExecutionTarget

    target = KubernetesExecutionTarget(FakeK8sJobTransport())
    dbg = target.prepare_debug(build_request("/app/x.py"))
    assert dbg.argv[:3] == ("python", "-m", "pdb")
    prof = target.prepare_profile(build_request("/app/x.py", profile_outfile="/tmp/out.prof"))
    assert "cProfile" in prof.argv
    assert "/tmp/out.prof" in prof.argv


def test_kubectl_transport_builds_run_argv():
    from utils.k8s_execution import SubprocessKubectlTransport

    transport = SubprocessKubectlTransport(
        image="python:3.11-slim",
        namespace="cdm",
        extra_kubectl_args=("--context=kind-codimension",),
    )
    argv = transport.build_run_argv("cdm-exec-1", ["python", "/app/a.py"], {"A": "1"})
    assert argv[0] == "kubectl"
    assert "--context=kind-codimension" in argv
    assert "run" in argv and "cdm-exec-1" in argv
    assert "--image=python:3.11-slim" in argv
    assert "--namespace=cdm" in argv
    assert "--env=A=1" in argv
    assert argv[-4:] == ["--command", "--", "python", "/app/a.py"]


def test_kubectl_transport_rejects_empty_image():
    from utils.k8s_execution import SubprocessKubectlTransport

    with pytest.raises(ValueError, match="image"):
        SubprocessKubectlTransport(image=" ")


def test_kubectl_available_is_bool():
    from utils.k8s_execution import kubectl_available

    assert isinstance(kubectl_available(), bool)


def test_r187_pod_name_not_argv_hash():
    from utils.k8s_execution import SubprocessKubectlTransport

    transport = SubprocessKubectlTransport()
    a = transport.allocate_pod_name()
    b = transport.allocate_pod_name()
    assert a != b
    assert a.startswith("cdm-exec-")
    assert "hash" not in a


def test_r187_wait_terminal_and_cleanup(monkeypatch):
    from utils.k8s_execution import SubprocessKubectlTransport

    transport = SubprocessKubectlTransport(wait_timeout_sec=2.0)
    phases = iter(["Pending", "Running", "Succeeded"])
    deleted: list[str] = []

    def fake_phase(_name):
        try:
            return next(phases)
        except StopIteration:
            return "Succeeded"

    monkeypatch.setattr(transport, "_pod_phase", fake_phase)
    monkeypatch.setattr(transport, "delete_pod", lambda name: deleted.append(name))
    monkeypatch.setattr(
        transport,
        "_kubectl",
        lambda *a, **k: type("R", (), {"returncode": 0, "stdout": "log\n", "stderr": ""})(),
    )

    import subprocess as sp

    def fake_run(argv, **kwargs):
        return sp.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(sp, "run", fake_run)
    code, out, err = transport.run_job(["python", "/app/x.py"])
    assert code == 0
    assert "log" in out
    assert deleted  # finally cleanup
