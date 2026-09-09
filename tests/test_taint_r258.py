# -*- coding: utf-8 -*-
"""R258: taint terminal-edge lattice — join only NORMAL branch exits."""

from __future__ import annotations

from core.taint import analyze_function_taint


def test_r258_return_arm_excluded_from_join() -> None:
    """``if cond: return`` must not keep pre-branch taint after a clean else."""
    src = (
        "def f(cond):\n"
        "    value = input()\n"
        "    if cond:\n"
        "        return\n"
        "    else:\n"
        "        value = 'safe'\n"
        "    eval(value)\n"
    )
    report = analyze_function_taint(src, function="f")
    assert report.empty


def test_r258_return_without_else_keeps_skip_path() -> None:
    """Bare ``if cond: return`` still falls through on the false path."""
    src = "def f(cond):\n    value = input()\n    if cond:\n        return\n    eval(value)\n"
    report = analyze_function_taint(src, function="f")
    assert not report.empty
    assert report.findings[0].source.startswith("call:input")


def test_r258_both_arms_return_skips_after() -> None:
    """When every arm returns, code after the ``if`` is unreachable."""
    src = "def f(cond, x):\n    if cond:\n        return\n    else:\n        return\n    eval(x)\n"
    report = analyze_function_taint(src, function="f")
    assert report.empty


def test_r258_raise_arm_excluded_from_join() -> None:
    """``raise`` is terminal and must not feed the fall-through join."""
    src = (
        "def f(cond):\n"
        "    value = input()\n"
        "    if cond:\n"
        "        raise RuntimeError('stop')\n"
        "    else:\n"
        "        value = 'safe'\n"
        "    eval(value)\n"
    )
    report = analyze_function_taint(src, function="f")
    assert report.empty


def test_r258_break_skips_loop_else() -> None:
    """``break`` must not pollute ``for``/``while`` else with early-exit taint."""
    src = (
        "def f(cond):\n"
        "    value = 'safe'\n"
        "    for _i in (1,):\n"
        "        if cond:\n"
        "            value = input()\n"
        "            break\n"
        "        value = 'safe'\n"
        "    else:\n"
        "        eval(value)\n"
    )
    report = analyze_function_taint(src, function="f")
    assert report.empty


def test_r258_break_reaches_after_loop() -> None:
    """Code after the loop still sees environments from ``break`` exits."""
    src = (
        "def f(cond):\n"
        "    value = 'safe'\n"
        "    for _i in (1,):\n"
        "        if cond:\n"
        "            value = input()\n"
        "            break\n"
        "    eval(value)\n"
    )
    report = analyze_function_taint(src, function="f")
    assert not report.empty
    assert report.findings[0].source.startswith("call:input")


def test_r258_continue_not_normal_body_exit_for_else() -> None:
    """``continue`` feeds the back-edge, not a normal body completion for else."""
    src = (
        "def f():\n"
        "    value = 'safe'\n"
        "    for _i in (1,):\n"
        "        value = input()\n"
        "        continue\n"
        "        value = 'dead'\n"
        "    else:\n"
        "        eval(value)\n"
    )
    report = analyze_function_taint(src, function="f")
    # Loop completes without break → else runs. Continue is not break, so else
    # is reachable; may-taint from iterations that continued should still reach
    # else via the fixpoint head / entry join used for else_in.
    assert not report.empty
    assert report.findings[0].source.startswith("call:input")


def test_r258_match_return_arm_excluded() -> None:
    """Match case that returns must not keep taint when other cases clean it."""
    src = (
        "def f(x):\n"
        "    y = input()\n"
        "    match x:\n"
        "        case 1:\n"
        "            return\n"
        "        case _:\n"
        "            y = 'safe'\n"
        "    eval(y)\n"
    )
    report = analyze_function_taint(src, function="f")
    assert report.empty
