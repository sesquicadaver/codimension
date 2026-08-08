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

"""Kubernetes ExecutionTarget MVP (R125).

Runs Python via an injectable ``K8sJobTransport`` that can create/wait a Job
(or a one-shot pod). Contract tests use ``FakeK8sJobTransport``; live clusters
may use ``SubprocessKubectlTransport`` (best-effort, unverified).

Lessons from R123/R124 applied here:
- prepare-only vs ``wait=True``
- script path is a **remote/in-cluster** path (image already contains code, or
  a volume mounts it) — no automatic sync in MVP
- debug/profile use in-pod ``pdb`` / ``cProfile``, not IDE TCP clients
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Mapping, Optional, Protocol, Sequence, runtime_checkable

from core.execution import ExecutionRequest, ExecutionResult, ExecutionTarget


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
    """Best-effort ``kubectl run`` / ``kubectl wait`` transport.

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
    ) -> None:
        if not image.strip():
            raise ValueError("image must be non-empty")
        self._image = image
        self._namespace = namespace
        self._kubectl_bin = kubectl_bin
        self._job_prefix = job_prefix
        self._extra_kubectl_args = tuple(extra_kubectl_args)

    @property
    def image(self) -> str:
        """Container image used for one-shot pods."""
        return self._image

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

    def run_job(
        self,
        argv: Sequence[str],
        *,
        env: Optional[Mapping[str, str]] = None,
        working_dir: Optional[str] = None,
    ) -> tuple[int, str, str]:
        """Create a one-shot pod, wait, fetch logs, delete."""
        del working_dir  # kubectl run --command does not map cwd portably in MVP
        name = f"{self._job_prefix}-{abs(hash(tuple(argv))) % 10_000_000}"
        create = subprocess.run(
            self.build_run_argv(name, argv, env),
            capture_output=True,
            text=True,
            check=False,
        )
        if create.returncode != 0:
            return int(create.returncode), create.stdout or "", create.stderr or ""

        wait = subprocess.run(
            [
                self._kubectl_bin,
                "wait",
                f"--namespace={self._namespace}",
                "--for=condition=Ready",
                f"pod/{name}",
                "--timeout=120s",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        # Ready may never fire for completed pods; fall through to logs/phase.
        _ = wait

        logs = subprocess.run(
            [self._kubectl_bin, "logs", f"--namespace={self._namespace}", name],
            capture_output=True,
            text=True,
            check=False,
        )
        phase = subprocess.run(
            [
                self._kubectl_bin,
                "get",
                "pod",
                name,
                f"--namespace={self._namespace}",
                "-o",
                "jsonpath={.status.phase}",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        subprocess.run(
            [self._kubectl_bin, "delete", "pod", name, f"--namespace={self._namespace}", "--ignore-not-found=true"],
            capture_output=True,
            text=True,
            check=False,
        )
        exit_code = 0 if (phase.stdout or "").strip() == "Succeeded" else 1
        if logs.returncode != 0 and exit_code == 0:
            exit_code = int(logs.returncode)
        return exit_code, logs.stdout or "", logs.stderr or create.stderr or ""


def kubectl_available(kubectl_bin: str = "kubectl") -> bool:
    """Return True when kubectl is on PATH (cluster reachability not checked)."""
    return shutil.which(kubectl_bin) is not None


class KubernetesExecutionTarget:
    """ExecutionTarget that executes via a ``K8sJobTransport``.

    By default methods only *prepare* the in-pod argv (``exit_code`` is
    ``None``). Pass ``wait=True`` to submit through the transport.
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

    def run(self, request: ExecutionRequest, *, wait: bool = False) -> ExecutionResult:
        """Build (and optionally execute) an in-pod run argv."""
        inner = [self._python, request.script, *request.args]
        return self._finish("run", inner, request, wait=wait)

    def debug(self, request: ExecutionRequest, *, wait: bool = False) -> ExecutionResult:
        """MVP: in-pod ``python -m pdb`` (no IDE TCP redirect)."""
        inner = [self._python, "-m", "pdb", request.script, *request.args]
        return self._finish("debug", inner, request, wait=wait)

    def profile(self, request: ExecutionRequest, *, wait: bool = False) -> ExecutionResult:
        """MVP: in-pod ``python -m cProfile``."""
        outfile = request.profile_outfile or "/tmp/codimension-profile.out"
        inner = [self._python, "-m", "cProfile", "-o", outfile, request.script, *request.args]
        return self._finish("profile", inner, request, wait=wait)

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

    def _finish(
        self,
        mode: str,
        inner_argv: Sequence[str],
        request: ExecutionRequest,
        *,
        wait: bool,
    ) -> ExecutionResult:
        """Attach metadata and optionally wait on the transport."""
        meta: dict[str, str] = {
            "mode": mode,
            "backend": "k8s",
            "cluster": self._cluster_label,
            "image": self._image,
            "sync": "in-image-or-volume-assumed",
        }
        argv = tuple(inner_argv)
        if not wait:
            # Surface a JSON Job stub in metadata for tooling without submitting.
            meta["job_stub"] = json.dumps(self.job_manifest_stub(request, mode=mode), sort_keys=True)
            return ExecutionResult(exit_code=None, argv=argv, metadata=meta)

        code, stdout, stderr = self._transport.run_job(
            inner_argv,
            env=request.env,
            working_dir=request.cwd,
        )
        return ExecutionResult(
            exit_code=int(code),
            argv=argv,
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
