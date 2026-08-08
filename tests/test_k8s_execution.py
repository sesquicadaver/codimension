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


def test_k8s_run_prepare_includes_job_stub():
    from core.execution import build_request
    from utils.k8s_execution import FakeK8sJobTransport, KubernetesExecutionTarget

    transport = FakeK8sJobTransport()
    target = KubernetesExecutionTarget(transport, image="python:3.12-slim")
    result = target.run(build_request("/app/main.py", ["--x"]))
    assert result.exit_code is None
    assert list(result.argv) == ["python", "/app/main.py", "--x"]
    assert transport.calls == []
    stub = json.loads(result.metadata["job_stub"])
    assert stub["kind"] == "Job"
    assert stub["spec"]["template"]["spec"]["containers"][0]["image"] == "python:3.12-slim"
    assert result.metadata["sync"] == "in-image-or-volume-assumed"


def test_k8s_run_wait_uses_transport():
    from core.execution import build_request
    from utils.k8s_execution import FakeK8sJobTransport, KubernetesExecutionTarget

    transport = FakeK8sJobTransport(exit_code=0, stdout="k8s-ok\n")
    target = KubernetesExecutionTarget(transport, python="python3")
    result = target.run(
        build_request("/app/main.py", ["a"], cwd="/app", env={"K": "1"}),
        wait=True,
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
    dbg = target.debug(build_request("/app/x.py"))
    assert dbg.argv[:3] == ("python", "-m", "pdb")
    prof = target.profile(build_request("/app/x.py", profile_outfile="/tmp/out.prof"))
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
