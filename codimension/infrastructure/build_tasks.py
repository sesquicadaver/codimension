# -*- coding: utf-8 -*-
#
# codimension - Cargo / CMake / Ninja / CTest task providers (R208)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Explicit build/test TaskProviders (R208).

Providers only **discover** argv plans from workspace markers. They never
spawn cargo/cmake/ninja/ctest, never run on file open, and never use
rust-analyzer or clangd as build runners.
"""

from __future__ import annotations

import os
import subprocess
from typing import Iterable, Mapping, Optional

from core.language_policy import require_build_task_exec
from core.tasks import BuildTask, CompositeTaskProvider, TaskKind, TaskPlan, prepare_task_plan


def _abs_root(workspace_root: str) -> str:
    """Normalize workspace root to an absolute path."""
    root = os.path.abspath(os.path.expanduser((workspace_root or "").strip() or "."))
    return root


def _marker(root: str, name: str) -> str | None:
    """Return absolute marker path when ``name`` exists under ``root``."""
    path = os.path.join(root, name)
    return path if os.path.isfile(path) else None


class CargoTaskProvider:
    """Discover Cargo check/test/clippy/fmt/build tasks when ``Cargo.toml`` exists."""

    provider_id = "cargo"

    _SPECS: tuple[tuple[str, str, TaskKind, tuple[str, ...]], ...] = (
        ("cargo.check", "Cargo check", TaskKind.CHECK, ("cargo", "check")),
        ("cargo.test", "Cargo test", TaskKind.TEST, ("cargo", "test")),
        ("cargo.clippy", "Cargo clippy", TaskKind.LINT, ("cargo", "clippy")),
        ("cargo.fmt_check", "Cargo fmt --check", TaskKind.FORMAT_CHECK, ("cargo", "fmt", "--check")),
        ("cargo.build", "Cargo build", TaskKind.BUILD, ("cargo", "build")),
    )

    def list_tasks(self, workspace_root: str) -> tuple[BuildTask, ...]:
        """Return Cargo tasks when ``Cargo.toml`` is present; else empty."""
        root = _abs_root(workspace_root)
        marker = _marker(root, "Cargo.toml")
        if marker is None:
            # Workspace member: Cargo.toml may sit one level up from a crate path
            # passed as root; still require the marker at the given root for
            # explicit per-workspace process keys (no walk into unrelated trees).
            return ()
        return tuple(
            BuildTask(
                task_id=task_id,
                label=label,
                kind=kind,
                argv=argv,
                cwd=root,
                provider_id=self.provider_id,
                language_id="rust",
                tool="cargo",
                marker_path=marker,
            )
            for task_id, label, kind, argv in self._SPECS
        )


class CMakeTaskProvider:
    """Discover CMake configure/build tasks when ``CMakeLists.txt`` exists."""

    provider_id = "cmake"

    def list_tasks(self, workspace_root: str) -> tuple[BuildTask, ...]:
        """Return configure + build plans; empty without ``CMakeLists.txt``."""
        root = _abs_root(workspace_root)
        marker = _marker(root, "CMakeLists.txt")
        if marker is None:
            return ()
        build_dir = os.path.join(root, "build")
        return (
            BuildTask(
                task_id="cmake.configure",
                label="CMake configure",
                kind=TaskKind.CONFIGURE,
                argv=("cmake", "-S", root, "-B", build_dir),
                cwd=root,
                provider_id=self.provider_id,
                language_id="cpp",
                tool="cmake",
                marker_path=marker,
            ),
            BuildTask(
                task_id="cmake.build",
                label="CMake build",
                kind=TaskKind.BUILD,
                argv=("cmake", "--build", build_dir),
                cwd=root,
                provider_id=self.provider_id,
                language_id="cpp",
                tool="cmake",
                marker_path=marker,
            ),
        )


class NinjaTaskProvider:
    """Discover Ninja build when ``build.ninja`` exists (root or ``build/``)."""

    provider_id = "ninja"

    def list_tasks(self, workspace_root: str) -> tuple[BuildTask, ...]:
        """Return a Ninja build task when a build graph is present."""
        root = _abs_root(workspace_root)
        for candidate in (
            os.path.join(root, "build.ninja"),
            os.path.join(root, "build", "build.ninja"),
        ):
            if os.path.isfile(candidate):
                cwd = os.path.dirname(candidate)
                return (
                    BuildTask(
                        task_id="ninja.build",
                        label="Ninja build",
                        kind=TaskKind.BUILD,
                        argv=("ninja",),
                        cwd=cwd,
                        provider_id=self.provider_id,
                        language_id="cpp",
                        tool="ninja",
                        marker_path=candidate,
                    ),
                )
        return ()


class CTestTaskProvider:
    """Discover CTest when a CTest testfile or CMake project is present."""

    provider_id = "ctest"

    def list_tasks(self, workspace_root: str) -> tuple[BuildTask, ...]:
        """Return a CTest task for ``build/`` or root when markers match."""
        root = _abs_root(workspace_root)
        for cwd, marker_name in (
            (os.path.join(root, "build"), "CTestTestfile.cmake"),
            (root, "CTestTestfile.cmake"),
        ):
            marker = os.path.join(cwd, marker_name)
            if os.path.isfile(marker):
                return (
                    BuildTask(
                        task_id="ctest.run",
                        label="CTest",
                        kind=TaskKind.TEST,
                        argv=("ctest", "--output-on-failure"),
                        cwd=cwd,
                        provider_id=self.provider_id,
                        language_id="cpp",
                        tool="ctest",
                        marker_path=marker,
                    ),
                )
        # Soft offer: CMake project without generated testfile yet — still
        # advertise explicit ctest in build/ (user runs after configure).
        cmake = _marker(root, "CMakeLists.txt")
        if cmake is not None:
            build_dir = os.path.join(root, "build")
            return (
                BuildTask(
                    task_id="ctest.run",
                    label="CTest",
                    kind=TaskKind.TEST,
                    argv=("ctest", "--output-on-failure"),
                    cwd=build_dir,
                    provider_id=self.provider_id,
                    language_id="cpp",
                    tool="ctest",
                    marker_path=cmake,
                ),
            )
        return ()


def make_rust_task_provider() -> CargoTaskProvider:
    """Return the Cargo task provider for Rust workspaces."""
    return CargoTaskProvider()


def make_cpp_task_provider() -> CompositeTaskProvider:
    """Return CMake + Ninja + CTest composite for C++ workspaces."""
    return CompositeTaskProvider(
        providers=(CMakeTaskProvider(), NinjaTaskProvider(), CTestTaskProvider()),
        provider_id="cpp.tasks",
    )


def resolve_task_binary(
    plan: TaskPlan,
    *,
    absolute_binary: str,
    allowlist: Iterable[str],
) -> TaskPlan:
    """Replace the plan's first argv token with an allowlisted absolute binary.

    Discovery keeps portable tool names (``cargo``, ``cmake``, …). Explicit
    execution must pass an absolute path through ``BUILD_TASK_EXEC``.
    """
    resolved = require_build_task_exec(absolute_binary, allowlist)
    argv = (resolved,) + tuple(plan.argv[1:])
    return TaskPlan(task=plan.task, argv=argv, cwd=plan.cwd, binary=resolved)


def run_build_task(
    task: BuildTask,
    *,
    absolute_binary: str,
    allowlist: Iterable[str],
    env: Optional[Mapping[str, str]] = None,
    timeout: Optional[float] = None,
) -> subprocess.CompletedProcess[str]:
    """Execute ``task`` after ``BUILD_TASK_EXEC`` allowlist check.

    Call only on explicit user action — never from file-open or LSP hooks.
    """
    plan = resolve_task_binary(
        prepare_task_plan(task),
        absolute_binary=absolute_binary,
        allowlist=allowlist,
    )
    return subprocess.run(
        list(plan.argv),
        cwd=plan.cwd,
        env=dict(env) if env is not None else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


__all__ = [
    "CMakeTaskProvider",
    "CTestTaskProvider",
    "CargoTaskProvider",
    "NinjaTaskProvider",
    "make_cpp_task_provider",
    "make_rust_task_provider",
    "resolve_task_binary",
    "run_build_task",
]
