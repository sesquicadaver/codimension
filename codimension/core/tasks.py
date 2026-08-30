# -*- coding: utf-8 -*-
#
# codimension - polyglot build/test TaskProvider contracts (R208)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Build/test TaskProvider contracts (R208).

Tasks are **explicit**: discovery via :meth:`TaskProvider.list_tasks` never
runs a build tool, and must not be triggered merely by opening a file.
Execution is a separate step gated by ``BUILD_TASK_EXEC`` (absolute binary
allowlist). LSP servers (rust-analyzer / clangd) are never build runners.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, Sequence, runtime_checkable


class TaskKind(str, Enum):
    """Stable task categories for UI grouping."""

    CONFIGURE = "configure"
    BUILD = "build"
    CHECK = "check"
    TEST = "test"
    LINT = "lint"
    FORMAT_CHECK = "format_check"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class BuildTask:
    """One explicit build/test/check task (argv plan, not an execution)."""

    task_id: str
    label: str
    kind: TaskKind
    argv: tuple[str, ...]
    cwd: str
    provider_id: str
    language_id: str = ""
    tool: str = ""
    marker_path: str = ""

    def __post_init__(self) -> None:
        """Reject empty identity or empty argv."""
        if not self.task_id.strip():
            raise ValueError("task_id must be non-empty")
        if not self.label.strip():
            raise ValueError("label must be non-empty")
        if not self.argv:
            raise ValueError("argv must be non-empty")
        if not isinstance(self.argv, tuple):
            object.__setattr__(self, "argv", tuple(self.argv))
        if not self.provider_id.strip():
            raise ValueError("provider_id must be non-empty")
        if not self.cwd.strip():
            raise ValueError("cwd must be non-empty")


@dataclass(frozen=True, slots=True)
class TaskPlan:
    """Prepared argv for an explicit task — not an execution."""

    task: BuildTask
    argv: tuple[str, ...]
    cwd: str
    binary: str

    def __post_init__(self) -> None:
        """Normalize argv to a tuple."""
        if not isinstance(self.argv, tuple):
            object.__setattr__(self, "argv", tuple(self.argv))


@runtime_checkable
class TaskProvider(Protocol):
    """Discovers explicit build/test tasks for a workspace root.

    Implementations must **not** spawn processes inside ``list_tasks``.
    """

    @property
    def provider_id(self) -> str:
        """Stable provider key (e.g. ``cargo``, ``cmake``)."""

    def list_tasks(self, workspace_root: str) -> tuple[BuildTask, ...]:
        """Return tasks for ``workspace_root`` when markers match; else empty."""


@dataclass
class CompositeTaskProvider:
    """Merge several :class:`TaskProvider` instances without spawning tools."""

    providers: tuple[TaskProvider, ...] = ()
    provider_id: str = "composite"

    def list_tasks(self, workspace_root: str) -> tuple[BuildTask, ...]:
        """Concatenate tasks from bound providers in registration order."""
        out: list[BuildTask] = []
        for provider in self.providers:
            out.extend(provider.list_tasks(workspace_root))
        return tuple(out)


def prepare_task_plan(task: BuildTask) -> TaskPlan:
    """Build a :class:`TaskPlan` from ``task`` without executing anything.

    The first argv element is treated as the tool binary token (often a bare
    name such as ``cargo``). Absolute resolution and allowlist checks belong
    to the execution gate in ``language_policy`` / infrastructure runners.
    """
    binary = str(task.argv[0])
    return TaskPlan(task=task, argv=tuple(task.argv), cwd=task.cwd, binary=binary)


def find_task(tasks: Sequence[BuildTask], task_id: str) -> BuildTask:
    """Return the task with ``task_id`` or raise ``KeyError``."""
    for task in tasks:
        if task.task_id == task_id:
            return task
    raise KeyError(task_id)


__all__ = [
    "BuildTask",
    "CompositeTaskProvider",
    "TaskKind",
    "TaskPlan",
    "TaskProvider",
    "find_task",
    "prepare_task_plan",
]
