# -*- coding: utf-8 -*-
#
# codimension - graphics python two-way code editor and analyzer
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Kubernetes ExecutionTarget MVP (R125 / R187).

Runs Python via an injectable ``K8sJobTransport`` that can create/wait a Job
(or a one-shot pod). Contract tests use ``FakeK8sJobTransport``; live clusters
may use ``SubprocessKubectlTransport`` (best-effort, unverified).

R187 / A205–A206:
- ``prepare_*`` vs ``run`` (execute by default)
- wait for terminal pod phase Succeeded/Failed (not Ready)
- stable UUID pod names (not ``hash(argv)``)
- pod delete always in ``finally``
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
import uuid
from typing import Mapping, Optional, Protocol, Sequence, runtime_checkable

from core.execution import (
    ExecutionPlan,
    ExecutionRequest,
    ExecutionResult,
    ExecutionTarget,
    plan_to_prepare_result,
)

_TERMINAL_PHASES = frozenset({"Succeeded", "Failed"})
_DEFAULT_WAIT_TIMEOUT_SEC = 120.0
_POLL_SEC = 0.5


@runtime_checkable
class K8sJobTransport(Protocol):
    """Minimal Job/pod runner for KubernetesExecutionTarget."""

    def run_job(
        self,
        argv: Sequence[str],
        *,
        env: Optional[Mapping[str, str]] = None,
        working_dir: Optional[str] = None,
    ) -> tuple[int, str, str]:
        """Execute ``argv`` in a Job/pod; return ``(exit, stdout, stderr)``."""


class FakeK8sJobTransport:
    """Recording transport for contract tests (no cluster)."""

    def __init__(self, *, exit_code: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.calls: list[tuple[tuple[str, ...], Optional[dict[str, str]], Optional[str]]] = []

    def run_job(
        self,
        argv: Sequence[str],
        *,
        env: Optional[Mapping[str, str]] = None,
        working_dir: Optional[str] = None,
    ) -> tuple[int, str, str]:
        env_copy = dict(env) if env is not None else None
        self.calls.append((tuple(argv), env_copy, working_dir))
        return self.exit_code, self.stdout, self.stderr


class SubprocessKubectlTransport:
    """Best-effort ``kubectl run`` transport with terminal wait + finally cleanup.

    Unverified against real multi-tenant clusters, custom CRDs, and Windows
    kubectl wrappers. Prefer FakeK8sJobTransport in CI.
    """

    def __init__(
        self,
        *,
        image: str = "python:3.12-slim",
        namespace: str = "default",
        kubectl_bin: str = "kubectl",
        job_prefix: str = "cdm-exec",
        extra_kubectl_args: Sequence[str] = (),
        wait_timeout_sec: float = _DEFAULT_WAIT_TIMEOUT_SEC,
    ) -> None:
        if not image.strip():
            raise ValueError("image must be non-empty")
        self._image = image
        self._namespace = namespace
        self._kubectl_bin = kubectl_bin
        self._job_prefix = job_prefix
        self._extra_kubectl_args = tuple(extra_kubectl_args)
        self._wait_timeout_sec = max(1.0, float(wait_timeout_sec))

    @property
    def image(self) -> str:
        """Container image used for one-shot pods."""
        return self._image

    def allocate_pod_name(self) -> str:
        """Return a unique DNS-1123-ish pod name (not derived from argv hash)."""
        return f"{self._job_prefix}-{uuid.uuid4().hex[:12]}"

    def build_run_argv(self, name: str, argv: Sequence[str], env: Optional[Mapping[str, str]]) -> list[str]:
        """Compose ``kubectl run`` argv for a one-shot pod."""
        cmd: list[str] = [self._kubectl_bin, *self._extra_kubectl_args, "run", name]
        cmd.extend(
            [
                "--restart=Never",
                f"--image={self._image}",
                f"--namespace={self._namespace}",
            ]
        )
        if env:
            for key, value in env.items():
                cmd.append(f"--env={key}={value}")
        cmd.extend(["--command", "--", *argv])
        return cmd

    def _kubectl(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self._kubectl_bin, *self._extra_kubectl_args, *args],
            capture_output=True,
            text=True,
            check=False,
        )

    def _pod_phase(self, name: str) -> str:
        result = self._kubectl(
            "get",
            "pod",
            name,
            f"--namespace={self._namespace}",
            "-o",
            "jsonpath={.status.phase}",
        )
        return (result.stdout or "").strip()

    def wait_for_terminal_phase(self, name: str, *, timeout_sec: Optional[float] = None) -> str:
        """Poll until pod phase is Succeeded/Failed or timeout (R187 / A206).

        Does **not** wait for Ready — completed pods often never become Ready.
        """
        limit = self._wait_timeout_sec if timeout_sec is None else max(1.0, float(timeout_sec))
        deadline = time.monotonic() + limit
        last = ""
        while time.monotonic() < deadline:
            last = self._pod_phase(name)
            if last in _TERMINAL_PHASES:
                return last
            time.sleep(_POLL_SEC)
        return last or "Unknown"

    def delete_pod(self, name: str) -> None:
        """Best-effort delete of the one-shot pod."""
        self._kubectl(
            "delete",
            "pod",
            name,
            f"--namespace={self._namespace}",
            "--ignore-not-found=true",
        )

    def run_job(
        self,
        argv: Sequence[str],
        *,
        env: Optional[Mapping[str, str]] = None,
        working_dir: Optional[str] = None,
    ) -> tuple[int, str, str]:
        """Create a one-shot pod, wait for terminal phase, fetch logs, delete."""
        del working_dir
        name = self.allocate_pod_name()
        create = subprocess.run(
            self.build_run_argv(name, argv, env),
            capture_output=True,
            text=True,
            check=False,
        )
        if create.returncode != 0:
            # Nothing durable created (or name collision) — still try delete.
            try:
                self.delete_pod(name)
            except Exception:
                pass
            return int(create.returncode), create.stdout or "", create.stderr or ""

        try:
            phase = self.wait_for_terminal_phase(name)
            logs = self._kubectl("logs", f"--namespace={self._namespace}", name)
            exit_code = 0 if phase == "Succeeded" else 1
            if phase not in _TERMINAL_PHASES:
                exit_code = 124  # timeout-like
            if logs.returncode != 0 and exit_code == 0:
                exit_code = int(logs.returncode)
            return exit_code, logs.stdout or "", logs.stderr or create.stderr or ""
        finally:
            self.delete_pod(name)


def kubectl_available(kubectl_bin: str = "kubectl") -> bool:
    """Return True when kubectl is on PATH (cluster reachability not checked)."""
    return shutil.which(kubectl_bin) is not None


class KubernetesExecutionTarget:
    """ExecutionTarget that executes via a ``K8sJobTransport``.

    Use ``prepare_*`` for argv-only plans (includes Job stub metadata).
    ``run`` / ``debug`` / ``profile`` submit through the transport by default.
    """

    def __init__(
        self,
        transport: K8sJobTransport,
        *,
        python: str = "python",
        cluster_label: str = "cluster",
        image: str = "python:3.12-slim",
    ) -> None:
        """Bind transport and in-pod interpreter.

        Args:
            transport: Fake or kubectl-backed transport.
            python: Interpreter path/name inside the pod.
            cluster_label: Label used in ``which_python`` / metadata.
            image: Image name recorded in metadata (transport may also use it).
        """
        self._transport = transport
        self._python = python
        self._cluster_label = cluster_label
        self._image = image

    @property
    def transport(self) -> K8sJobTransport:
        """Bound Kubernetes transport."""
        return self._transport

    def which_python(self) -> str:
        """Return a backend-qualified in-cluster interpreter id."""
        return f"k8s:{self._cluster_label}:{self._python}"

    def prepare_run(self, request: ExecutionRequest) -> ExecutionPlan:
        """Return in-pod run argv without submitting."""
        inner = [self._python, request.script, *request.args]
        return self._plan("run", inner, request)

    def prepare_debug(self, request: ExecutionRequest) -> ExecutionPlan:
        """Return in-pod pdb argv without submitting."""
        inner = [self._python, "-m", "pdb", request.script, *request.args]
        return self._plan("debug", inner, request)

    def prepare_profile(self, request: ExecutionRequest) -> ExecutionPlan:
        """Return in-pod cProfile argv without submitting."""
        outfile = request.profile_outfile or "/tmp/codimension-profile.out"
        inner = [self._python, "-m", "cProfile", "-o", outfile, request.script, *request.args]
        return self._plan("profile", inner, request)

    def run(self, request: ExecutionRequest, *, wait: bool = True) -> ExecutionResult:
        """Submit an in-pod run (default) or return prepare-shaped result."""
        return self._finish(self.prepare_run(request), request, wait=wait)

    def debug(self, request: ExecutionRequest, *, wait: bool = True) -> ExecutionResult:
        """Submit in-pod pdb (default) or return prepare-shaped result."""
        return self._finish(self.prepare_debug(request), request, wait=wait)

    def profile(self, request: ExecutionRequest, *, wait: bool = True) -> ExecutionResult:
        """Submit in-pod cProfile (default) or return prepare-shaped result."""
        return self._finish(self.prepare_profile(request), request, wait=wait)

    def job_manifest_stub(self, request: ExecutionRequest, mode: str = "run") -> dict[str, object]:
        """Return a minimal Job-like dict for docs/tests (not submitted)."""
        if mode == "debug":
            container_cmd = [self._python, "-m", "pdb", request.script, *request.args]
        elif mode == "profile":
            outfile = request.profile_outfile or "/tmp/codimension-profile.out"
            container_cmd = [self._python, "-m", "cProfile", "-o", outfile, request.script, *request.args]
        else:
            container_cmd = [self._python, request.script, *request.args]
        return {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {"name": "cdm-exec-mvp", "labels": {"app": "codimension-exec"}},
            "spec": {
                "template": {
                    "spec": {
                        "restartPolicy": "Never",
                        "containers": [
                            {
                                "name": "exec",
                                "image": self._image,
                                "command": list(container_cmd),
                                "env": [{"name": key, "value": value} for key, value in (request.env or {}).items()],
                            }
                        ],
                    }
                }
            },
        }

    def _plan(self, mode: str, inner_argv: Sequence[str], request: ExecutionRequest) -> ExecutionPlan:
        meta: dict[str, str] = {
            "mode": mode,
            "backend": "k8s",
            "cluster": self._cluster_label,
            "image": self._image,
            "sync": "in-image-or-volume-assumed",
            "job_stub": json.dumps(self.job_manifest_stub(request, mode=mode), sort_keys=True),
        }
        return ExecutionPlan(mode=mode, argv=tuple(inner_argv), metadata=meta)

    def _finish(self, plan: ExecutionPlan, request: ExecutionRequest, *, wait: bool) -> ExecutionResult:
        """Submit via transport or return prepare-only when ``wait=False``."""
        if not wait:
            return plan_to_prepare_result(plan)

        code, stdout, stderr = self._transport.run_job(
            plan.argv,
            env=request.env,
            working_dir=request.cwd,
        )
        meta = {k: v for k, v in plan.metadata.items() if k != "job_stub"}
        return ExecutionResult(
            exit_code=int(code),
            argv=plan.argv,
            stdout=stdout,
            stderr=stderr,
            metadata=meta,
        )


def kubernetes_execution_target(
    transport: K8sJobTransport,
    *,
    python: str = "python",
    cluster_label: str = "cluster",
    image: str = "python:3.12-slim",
) -> ExecutionTarget:
    """Factory returning a typed ``ExecutionTarget`` for Kubernetes runs."""
    return KubernetesExecutionTarget(
        transport,
        python=python,
        cluster_label=cluster_label,
        image=image,
    )
