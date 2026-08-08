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

"""Docker ExecutionTarget MVP (R123).

Builds ``docker run`` argv that mounts a host workspace and executes the
request script with the container interpreter. No GUI; headless-friendly.

Debug/profile MVP uses in-container ``pdb`` / ``cProfile`` (not the IDE TCP
redirect clients — those stay on LocalExecutionTarget until a later task).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Sequence

from core.execution import ExecutionRequest, ExecutionResult, ExecutionTarget


def docker_available(docker_bin: str = "docker") -> bool:
    """Return True when the docker CLI is on PATH and the daemon answers."""
    binary = shutil.which(docker_bin)
    if not binary:
        return False
    try:
        completed = subprocess.run(
            [binary, "info"],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


class DockerExecutionTarget:
    """ExecutionTarget that runs Python inside a Docker container.

    By default methods only *prepare* argv (``exit_code`` is ``None``). Pass
    ``wait=True`` to execute ``docker run`` synchronously (integration tests).
    """

    def __init__(
        self,
        workspace: str,
        *,
        image: str = "python:3.12-slim",
        python: str = "python",
        docker_bin: str = "docker",
        container_workdir: str = "/workspace",
        extra_run_args: Sequence[str] = (),
    ) -> None:
        """Bind image, host workspace mount, and container interpreter.

        Args:
            workspace: Absolute host directory mounted into the container.
            image: Docker image that provides a Python interpreter.
            python: Interpreter path/name inside the container.
            docker_bin: Docker CLI executable name or path.
            container_workdir: Mount point / ``-w`` inside the container.
            extra_run_args: Extra ``docker run`` flags (e.g. ``--network=host``).
        """
        host = os.path.abspath(workspace)
        if not os.path.isdir(host):
            raise ValueError(f"workspace is not a directory: {workspace!r}")
        self._workspace = host
        self._image = image
        self._python = python
        self._docker_bin = docker_bin
        self._container_workdir = container_workdir.rstrip("/") or "/workspace"
        self._extra_run_args = tuple(extra_run_args)

    @property
    def workspace(self) -> str:
        """Absolute host workspace path."""
        return self._workspace

    @property
    def image(self) -> str:
        """Docker image used for runs."""
        return self._image

    def which_python(self) -> str:
        """Return a backend-qualified interpreter id for the container python."""
        return f"docker:{self._image}:{self._python}"

    def map_to_container(self, host_path: str) -> str:
        """Map a host path under the workspace to the container mount path.

        Paths outside the workspace are rejected so the container cannot be
        pointed at unmounted host files by accident.
        """
        abs_path = os.path.abspath(host_path)
        workspace = self._workspace
        if abs_path == workspace:
            return self._container_workdir
        prefix = workspace + os.sep
        if not abs_path.startswith(prefix):
            raise ValueError(
                f"script {host_path!r} is outside workspace {workspace!r}"
            )
        rel = abs_path[len(prefix) :].replace(os.sep, "/")
        return f"{self._container_workdir}/{rel}"

    def run(self, request: ExecutionRequest, *, wait: bool = False) -> ExecutionResult:
        """Build (and optionally execute) a dockerized run argv."""
        script = self.map_to_container(request.script)
        inner = [self._python, script, *request.args]
        return self._finish("run", inner, request, wait=wait)

    def debug(self, request: ExecutionRequest, *, wait: bool = False) -> ExecutionResult:
        """MVP: run under in-container ``pdb`` (no IDE TCP redirect)."""
        script = self.map_to_container(request.script)
        inner = [self._python, "-m", "pdb", script, *request.args]
        return self._finish("debug", inner, request, wait=wait)

    def profile(self, request: ExecutionRequest, *, wait: bool = False) -> ExecutionResult:
        """MVP: run under in-container ``cProfile``."""
        script = self.map_to_container(request.script)
        outfile = request.profile_outfile
        if outfile:
            try:
                out_mapped = self.map_to_container(outfile)
            except ValueError:
                out_mapped = outfile
        else:
            out_mapped = f"{self._container_workdir}/.codimension-profile.out"
        inner = [self._python, "-m", "cProfile", "-o", out_mapped, script, *request.args]
        return self._finish("profile", inner, request, wait=wait)

    def build_docker_argv(self, inner_argv: Sequence[str], request: ExecutionRequest) -> list[str]:
        """Compose ``docker run … image <inner_argv>`` for the bound workspace."""
        mount = f"{self._workspace}:{self._container_workdir}"
        workdir = self._container_workdir
        if request.cwd:
            try:
                workdir = self.map_to_container(request.cwd)
            except ValueError:
                # Keep default workdir when cwd is outside the mounted tree.
                pass
        argv = [
            self._docker_bin,
            "run",
            "--rm",
            "-v",
            mount,
            "-w",
            workdir,
        ]
        if request.env:
            for key, value in request.env.items():
                argv.extend(["-e", f"{key}={value}"])
        argv.extend(self._extra_run_args)
        argv.append(self._image)
        argv.extend(list(inner_argv))
        return argv

    def _finish(
        self,
        mode: str,
        inner_argv: Sequence[str],
        request: ExecutionRequest,
        *,
        wait: bool,
    ) -> ExecutionResult:
        """Attach metadata and optionally wait on ``docker run``."""
        argv = self.build_docker_argv(inner_argv, request)
        meta: dict[str, str] = {
            "mode": mode,
            "backend": "docker",
            "image": self._image,
            "workspace": self._workspace,
        }
        if not wait:
            return ExecutionResult(exit_code=None, argv=tuple(argv), metadata=meta)

        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
        )
        return ExecutionResult(
            exit_code=int(completed.returncode),
            argv=tuple(argv),
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
            metadata=meta,
        )


def docker_execution_target(
    workspace: str,
    *,
    image: str = "python:3.12-slim",
    python: str = "python",
    docker_bin: str = "docker",
    container_workdir: str = "/workspace",
    extra_run_args: Sequence[str] = (),
) -> ExecutionTarget:
    """Factory returning a typed ``ExecutionTarget`` for Docker runs."""
    return DockerExecutionTarget(
        workspace,
        image=image,
        python=python,
        docker_bin=docker_bin,
        container_workdir=container_workdir,
        extra_run_args=extra_run_args,
    )
