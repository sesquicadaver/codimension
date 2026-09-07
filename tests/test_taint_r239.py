# -*- coding: utf-8 -*-
"""R239: forward CFG worklist for function-local taint (no whole-list re-exec)."""

from __future__ import annotations

from core.taint import analyze_function_taint


def test_r239_sink_before_source_no_false_positive() -> None:
    """Whole-list re-exec must not make a later source taint an earlier sink."""
    src = "def f():\n    eval(value)\n    value = input()\n"
    report = analyze_function_taint(src, function="f")
    assert report.empty
    assert "value" in report.tainted_names


def test_r239_exception_handler_sees_mid_try_taint() -> None:
    """Handlers join throw points after body statements, not only pre-try."""
    src = (
        "def f():\n"
        "    try:\n"
        "        value = input()\n"
        "        raise RuntimeError('boom')\n"
        "    except Exception:\n"
        "        eval(value)\n"
    )
    report = analyze_function_taint(src, function="f")
    assert not report.empty
    assert report.findings[0].sink == "eval"
    assert report.findings[0].source.startswith("call:input")


def test_r239_non_exhaustive_match_no_match_fallthrough() -> None:
    """Without an irrefutable case, pre-match taint survives to the join."""
    src = (
        "def f(x):\n"
        "    y = input()\n"
        "    match x:\n"
        "        case 1:\n"
        "            y = 'safe'\n"
        "    eval(y)\n"
    )
    report = analyze_function_taint(src, function="f")
    assert not report.empty
    assert report.findings[0].source.startswith("call:input")


def test_r239_exhaustive_match_no_fallthrough_clears() -> None:
    """Irrefutable case covers all paths; clean arms clear prior taint."""
    src = (
        "def f(x):\n"
        "    y = input()\n"
        "    match x:\n"
        "        case _:\n"
        "            y = 'safe'\n"
        "    eval(y)\n"
    )
    report = analyze_function_taint(src, function="f")
    assert report.empty


def test_r239_loop_else_sees_body_termination_taint() -> None:
    """Loop else uses normal-termination state after the body, not only entry."""
    src = (
        "def f():\n"
        "    for _i in (1,):\n"
        "        value = input()\n"
        "    else:\n"
        "        eval(value)\n"
    )
    report = analyze_function_taint(src, function="f")
    assert not report.empty
    assert report.findings[0].sink == "eval"
    assert report.findings[0].source.startswith("call:input")


def test_r239_while_fixpoint_propagates_across_back_edge() -> None:
    """Local loop fixpoint must carry taint across the back-edge."""
    src = (
        "def f(cond):\n"
        "    x = 'safe'\n"
        "    y = 'safe'\n"
        "    while cond:\n"
        "        y = x\n"
        "        x = input()\n"
        "    eval(y)\n"
    )
    report = analyze_function_taint(src, function="f")
    assert not report.empty
    assert report.findings[0].source.startswith("call:input")
