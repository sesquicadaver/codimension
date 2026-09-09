# -*- coding: utf-8 -*-
"""R267: multi-exit taint envs — finally per edge; nested loop exit bubbling."""

from __future__ import annotations

from core.taint import ExitKind, analyze_function_taint


def test_r267_finally_sees_taint_from_return_arm_not_only_raise() -> None:
    """``finally`` must observe every terminal edge env (return ∪ raise), not one."""
    src = (
        "def f(cond):\n"
        "    try:\n"
        "        if cond:\n"
        "            x = input()\n"
        "            return\n"
        "        else:\n"
        "            x = 'safe'\n"
        "            raise RuntimeError('x')\n"
        "    finally:\n"
        "        eval(x)\n"
    )
    report = analyze_function_taint(src, function="f")
    assert not report.empty
    assert report.findings[0].source.startswith("call:input")


def test_r267_finally_per_edge_preserves_clean_path_absence() -> None:
    """When every edge into ``finally`` is clean, no finding."""
    src = (
        "def f(cond):\n"
        "    try:\n"
        "        if cond:\n"
        "            x = 'a'\n"
        "            return\n"
        "        else:\n"
        "            x = 'b'\n"
        "            raise RuntimeError('x')\n"
        "    finally:\n"
        "        eval(x)\n"
    )
    report = analyze_function_taint(src, function="f")
    assert report.empty


def test_r267_nested_loop_outer_break_still_joins_after() -> None:
    """Inner loop must not disable outer break/continue collection (R267)."""
    src = (
        "def f(cond):\n"
        "    value = 'safe'\n"
        "    for _i in (1,):\n"
        "        for _j in (1,):\n"
        "            pass\n"
        "        if cond:\n"
        "            value = input()\n"
        "            break\n"
        "    eval(value)\n"
    )
    report = analyze_function_taint(src, function="f")
    assert not report.empty
    assert report.findings[0].source.startswith("call:input")


def test_r267_nested_inner_break_does_not_skip_outer_else() -> None:
    """Inner ``break`` must not be attributed to the outer loop's else-skip lattice."""
    src = (
        "def f(cond):\n"
        "    value = 'safe'\n"
        "    for _i in (1,):\n"
        "        for _j in (1,):\n"
        "            if cond:\n"
        "                value = input()\n"
        "                break\n"
        "        value = 'safe'\n"
        "    else:\n"
        "        eval(value)\n"
    )
    report = analyze_function_taint(src, function="f")
    assert report.empty


def test_r267_try_return_still_runs_finally_sink() -> None:
    src = "def f():\n    x = input()\n    try:\n        return\n    finally:\n        eval(x)\n"
    report = analyze_function_taint(src, function="f")
    assert not report.empty


def test_r267_exit_envs_merge_same_kind() -> None:
    """Two return arms may-join under ``RETURN`` before ``finally``."""
    src = (
        "def f(cond):\n"
        "    try:\n"
        "        if cond:\n"
        "            x = input()\n"
        "            return\n"
        "        else:\n"
        "            x = 'safe'\n"
        "            return\n"
        "    finally:\n"
        "        eval(x)\n"
    )
    report = analyze_function_taint(src, function="f")
    assert not report.empty
    assert report.findings[0].source.startswith("call:input")


def test_r267_exit_kind_enum_stable() -> None:
    assert ExitKind.RETURN.value == "return"
    assert ExitKind.BREAK.value == "break"
