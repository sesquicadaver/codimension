# -*- coding: utf-8 -*-
"""R208: Cargo / CMake / Ninja / CTest TaskProviders (explicit only)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from core.language import LanguageCapability, make_cpp_language_service, make_rust_language_service
from core.language_policy import BuildTaskExecError, PolicyCapability, require_build_task_exec
from core.tasks import TaskKind, find_task, prepare_task_plan
from infrastructure.build_tasks import (
    CargoTaskProvider,
    CMakeTaskProvider,
    CTestTaskProvider,
    NinjaTaskProvider,
    make_cpp_task_provider,
    make_rust_task_provider,
    resolve_task_binary,
    run_build_task,
)


def test_build_task_exec_capability_and_deny() -> None:
    assert PolicyCapability.BUILD_TASK_EXEC.value == "build_task_exec"
    with pytest.raises(BuildTaskExecError):
        require_build_task_exec("cargo", ["/usr/bin/cargo"])
    with pytest.raises(BuildTaskExecError):
        require_build_task_exec("/usr/bin/cargo", [])


def test_cargo_tasks_require_marker(tmp_path: Path) -> None:
    provider = CargoTaskProvider()
    assert provider.list_tasks(str(tmp_path)) == ()
    (tmp_path / "Cargo.toml").write_text("[package]\nname='x'\n", encoding="utf-8")
    tasks = provider.list_tasks(str(tmp_path))
    ids = {t.task_id for t in tasks}
    assert ids == {
        "cargo.check",
        "cargo.test",
        "cargo.clippy",
        "cargo.fmt_check",
        "cargo.build",
    }
    check = find_task(tasks, "cargo.check")
    assert check.kind is TaskKind.CHECK
    assert check.argv == ("cargo", "check")
    assert check.cwd == str(tmp_path.resolve())
    assert check.language_id == "rust"
    plan = prepare_task_plan(check)
    assert plan.binary == "cargo"
    assert plan.argv[0] == "cargo"


def test_cmake_ninja_ctest_discovery(tmp_path: Path) -> None:
    assert CMakeTaskProvider().list_tasks(str(tmp_path)) == ()
    assert NinjaTaskProvider().list_tasks(str(tmp_path)) == ()
    assert CTestTaskProvider().list_tasks(str(tmp_path)) == ()

    (tmp_path / "CMakeLists.txt").write_text("project(x)\n", encoding="utf-8")
    cmake = CMakeTaskProvider().list_tasks(str(tmp_path))
    assert {t.task_id for t in cmake} == {"cmake.configure", "cmake.build"}
    configure = find_task(cmake, "cmake.configure")
    assert configure.kind is TaskKind.CONFIGURE
    assert configure.argv[0] == "cmake"
    assert "-S" in configure.argv and "-B" in configure.argv

    soft_ctest = CTestTaskProvider().list_tasks(str(tmp_path))
    assert soft_ctest[0].task_id == "ctest.run"
    assert soft_ctest[0].cwd.endswith("build")

    build = tmp_path / "build"
    build.mkdir()
    (build / "build.ninja").write_text("# ninja\n", encoding="utf-8")
    (build / "CTestTestfile.cmake").write_text("# ctest\n", encoding="utf-8")
    ninja = NinjaTaskProvider().list_tasks(str(tmp_path))
    assert ninja[0].task_id == "ninja.build"
    assert ninja[0].cwd == str(build.resolve())
    assert ninja[0].argv == ("ninja",)
    ctest = CTestTaskProvider().list_tasks(str(tmp_path))
    assert ctest[0].argv[0] == "ctest"
    assert ctest[0].cwd == str(build.resolve())


def test_cpp_composite_and_capability() -> None:
    rust = make_rust_language_service(tasks=make_rust_task_provider())
    assert rust.has_capability(LanguageCapability.BUILD_TASKS)
    assert rust.tasks is not None
    cpp = make_cpp_language_service(tasks=make_cpp_task_provider())
    assert cpp.has_capability(LanguageCapability.BUILD_TASKS)
    bare = make_rust_language_service()
    assert not bare.has_capability(LanguageCapability.BUILD_TASKS)


def test_list_tasks_does_not_spawn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "Cargo.toml").write_text("[package]\nname='x'\n", encoding="utf-8")
    (tmp_path / "CMakeLists.txt").write_text("project(x)\n", encoding="utf-8")

    def _boom(*_a: object, **_k: object) -> None:
        raise AssertionError("list_tasks must not spawn subprocesses")

    monkeypatch.setattr("subprocess.run", _boom)
    monkeypatch.setattr("subprocess.Popen", _boom)
    monkeypatch.setattr("os.system", _boom)
    assert CargoTaskProvider().list_tasks(str(tmp_path))
    assert make_cpp_task_provider().list_tasks(str(tmp_path))


def test_resolve_and_run_gated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "Cargo.toml").write_text("[package]\nname='x'\n", encoding="utf-8")
    task = find_task(CargoTaskProvider().list_tasks(str(tmp_path)), "cargo.check")
    tool = tmp_path / "fake-cargo"
    tool.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    tool.chmod(0o755)
    plan = resolve_task_binary(
        prepare_task_plan(task),
        absolute_binary=str(tool),
        allowlist=[str(tool)],
    )
    assert plan.argv[0] == os.path.realpath(tool)
    with pytest.raises(BuildTaskExecError):
        resolve_task_binary(
            prepare_task_plan(task),
            absolute_binary=str(tool),
            allowlist=[],
        )

    calls: list[list[str]] = []

    class _Done:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def _run(argv: list[str], **kwargs: object) -> _Done:
        calls.append(list(argv))
        assert kwargs.get("cwd") == str(tmp_path.resolve())
        return _Done()

    monkeypatch.setattr("subprocess.run", _run)
    result = run_build_task(task, absolute_binary=str(tool), allowlist=[str(tool)])
    assert result.returncode == 0
    assert calls and calls[0][0] == os.path.realpath(tool)
    assert calls[0][1:] == ["check"]
