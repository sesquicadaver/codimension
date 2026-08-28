# -*- coding: utf-8 -*-
"""R143: function-local taint / data-flow MVP."""

from __future__ import annotations

from pathlib import Path

import pytest
from core.taint import (
    DEFAULT_SINK_CALLS,
    analyze_function_taint,
    analyze_function_taint_from_file,
)


def test_param_flows_to_eval() -> None:
    report = analyze_function_taint(
        "def f(x):\n    eval(x)\n",
        function="f",
    )
    assert not report.empty
    assert report.heuristic is True
    assert 0.0 < report.confidence < 1.0
    assert report.parameters == ("x",)
    finding = report.findings[0]
    assert finding.sink == "eval"
    assert finding.source == "param:x"
    assert finding.via_names == ("x",)


def test_input_source_to_os_system() -> None:
    src = "import os\n\ndef g():\n    y = input()\n    os.system(y)\n"
    report = analyze_function_taint(src, function="g")
    assert len(report.findings) == 1
    assert report.findings[0].sink == "os.system"
    assert report.findings[0].source.startswith("call:input")


def test_clean_value_does_not_taint_sink() -> None:
    report = analyze_function_taint(
        "def f(x):\n    y = 1\n    eval(y)\n",
        function="f",
    )
    assert report.empty


def test_propagation_through_concat_and_subprocess() -> None:
    src = "import subprocess\n\ndef f(cmd):\n    z = cmd + ' --help'\n    subprocess.run(z)\n"
    report = analyze_function_taint(src, function="f")
    assert report.findings
    assert report.findings[0].sink == "subprocess.run"
    assert report.findings[0].source == "param:cmd"


def test_overwrite_clears_taint() -> None:
    report = analyze_function_taint(
        "def f(x):\n    x = 'safe'\n    eval(x)\n",
        function="f",
    )
    assert report.empty


def test_named_method_on_class() -> None:
    src = "class C:\n    def handle(self, payload):\n        exec(payload)\n"
    report = analyze_function_taint(src, function="handle")
    assert report.findings
    assert report.findings[0].sink == "exec"
    assert report.findings[0].source == "param:payload"


def test_missing_function_raises() -> None:
    with pytest.raises(ValueError, match="not found"):
        analyze_function_taint("def f():\n    pass\n", function="missing")


def test_default_sink_catalog_covers_mvp() -> None:
    assert "eval" in DEFAULT_SINK_CALLS
    assert "subprocess.Popen" in DEFAULT_SINK_CALLS


def test_from_file(tmp_path: Path) -> None:
    path = tmp_path / "sample.py"
    path.write_text("def f(a):\n    eval(a)\n", encoding="utf-8")
    report = analyze_function_taint_from_file(str(path), function="f")
    assert report.findings
