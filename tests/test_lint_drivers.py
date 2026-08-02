# -*- coding: utf-8 -*-
"""Tests for lint driver JSON parseOutput implementations."""

import importlib.util
import json
import os
import sys
import types
from datetime import datetime

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CDMPLUGINS_DIR = os.path.join(ROOT, "cdmplugins")
CODMENSION_DIR = os.path.join(ROOT, "codimension")


def _setup_lint_driver_import_stubs():
    """Stub Qt/utils imports required by lintdriverbase and drivers."""
    ui_pkg = types.ModuleType("ui")
    ui_pkg.__path__ = [os.path.join(CODMENSION_DIR, "ui")]
    sys.modules["ui"] = ui_pkg

    qt_mod = types.ModuleType("ui.qt")

    class _QWidget:
        def __init__(self, *_args, **_kwargs):
            pass

    class _Signal:
        def connect(self, *_args, **_kwargs):
            return None

        def emit(self, *_args, **_kwargs):
            return None

    class _pyqtSignal:
        def __init__(self, *_args, **_kwargs):
            pass

        def connect(self, *_args, **_kwargs):
            return None

        def emit(self, *_args, **_kwargs):
            return None

    class _QByteArray:
        def __init__(self):
            self._data = b""

        def __iadd__(self, other):
            self._data += bytes(other)
            return self

        def size(self):
            return len(self._data)

        def data(self):
            return self._data

    class _QTimer:
        def __init__(self, *_args, **_kwargs):
            self._cb = None

        def setSingleShot(self, *_args, **_kwargs):
            return None

        def timeout(self):
            return _Signal()

        def start(self, *_args, **_kwargs):
            return None

        def stop(self):
            return None

    class _QProcess:
        SeparateChannels = 0
        StandardOutput = 1
        StandardError = 2
        Running = 3
        NotRunning = 0

        def __init__(self, *_args, **_kwargs):
            self._env = None
            self.errorOccurred = _Signal()
            self.readyReadStandardOutput = _Signal()
            self.readyReadStandardError = _Signal()
            self.finished = _Signal()

        def setProcessChannelMode(self, *_args, **_kwargs):
            return None

        def setWorkingDirectory(self, *_args, **_kwargs):
            return None

        def setProcessEnvironment(self, env):
            self._env = env

        def start(self, *_args, **_kwargs):
            return None

        def waitForStarted(self):
            return True

        def state(self):
            return self.Running

        def terminate(self):
            return None

        def kill(self):
            return None

        def waitForFinished(self, *_args, **_kwargs):
            return None

        def setReadChannel(self, *_args, **_kwargs):
            return None

        def bytesAvailable(self):
            return 0

        def readAllStandardOutput(self):
            return _QByteArray()

        def readAllStandardError(self):
            return _QByteArray()

    class _QProcessEnvironment:
        def __init__(self):
            self._values = dict(os.environ)

        @classmethod
        def systemEnvironment(cls):
            return cls()

        def insert(self, key, value):
            self._values[key] = value

        def value(self, key, default=""):
            return self._values.get(key, default)

        def contains(self, key):
            return key in self._values

    qt_mod.QWidget = _QWidget
    qt_mod.pyqtSignal = _pyqtSignal
    qt_mod.QByteArray = _QByteArray
    qt_mod.QProcess = _QProcess
    qt_mod.QProcessEnvironment = _QProcessEnvironment
    qt_mod.QTimer = _QTimer
    sys.modules["ui.qt"] = qt_mod

    utils_pkg = types.ModuleType("utils")
    utils_pkg.__path__ = [os.path.join(CODMENSION_DIR, "utils")]
    sys.modules["utils"] = utils_pkg

    misc_mod = types.ModuleType("utils.misc")
    misc_mod.getLocaleDateTime = lambda: datetime(2026, 7, 4)
    sys.modules["utils.misc"] = misc_mod

    run_mod = types.ModuleType("utils.run")
    run_mod.getProjectPythonPath = lambda _project: "python"
    sys.modules["utils.run"] = run_mod

    cdmplugins_pkg = types.ModuleType("cdmplugins")
    cdmplugins_pkg.__path__ = [CDMPLUGINS_DIR]
    sys.modules["cdmplugins"] = cdmplugins_pkg


def _load_driver(module_name, file_name):
    """Load a lint driver module without plugin package side effects."""
    _setup_lint_driver_import_stubs()
    # process_env
    pe_path = os.path.join(CDMPLUGINS_DIR, "process_env.py")
    pe_spec = importlib.util.spec_from_file_location("cdmplugins.process_env", pe_path)
    pe_mod = importlib.util.module_from_spec(pe_spec)
    sys.modules["cdmplugins.process_env"] = pe_mod
    pe_spec.loader.exec_module(pe_mod)

    base_path = os.path.join(CDMPLUGINS_DIR, "lintdriverbase.py")
    base_spec = importlib.util.spec_from_file_location("cdmplugins.lintdriverbase", base_path)
    base_mod = importlib.util.module_from_spec(base_spec)
    sys.modules["cdmplugins.lintdriverbase"] = base_mod
    base_spec.loader.exec_module(base_mod)

    driver_path = os.path.join(CDMPLUGINS_DIR, file_name)
    driver_spec = importlib.util.spec_from_file_location(module_name, driver_path)
    driver_mod = importlib.util.module_from_spec(driver_spec)
    sys.modules[module_name] = driver_mod
    driver_spec.loader.exec_module(driver_mod)
    return driver_mod


def test_ruff_parse_output():
    """RuffDriver maps JSON diagnostics into results."""
    mod = _load_driver("cdmplugins.ruff.ruffdriver", "ruff/ruffdriver.py")
    driver = mod.RuffDriver(None)
    results = {"Diagnostics": []}
    stdout = json.dumps(
        [
            {
                "code": "E101",
                "message": "indentation contains mixed spaces and tabs",
                "filename": "sample.py",
                "location": {"row": 3, "column": 1},
                "end_location": {"row": 3, "column": 5},
            }
        ]
    )
    driver.parseOutput(stdout, "", results)
    assert len(results["Diagnostics"]) == 1
    diag = results["Diagnostics"][0]
    assert diag["code"] == "E101"
    assert diag["line"] == 3
    assert diag["column"] == 1
    assert diag["end_line"] == 3
    assert diag["end_column"] == 5


def test_bandit_parse_output():
    """BanditDriver maps JSON results into diagnostics."""
    mod = _load_driver("cdmplugins.bandit.banditdriver", "bandit/banditdriver.py")
    driver = mod.BanditDriver(None)
    results = {"Diagnostics": []}
    stdout = json.dumps(
        {
            "results": [
                {
                    "line_number": 12,
                    "test_id": "B101",
                    "issue_text": "Test for use of assert",
                    "issue_severity": "LOW",
                    "issue_confidence": "HIGH",
                }
            ]
        }
    )
    driver.parseOutput(stdout, "", results)
    assert len(results["Diagnostics"]) == 1
    diag = results["Diagnostics"][0]
    assert diag["code"] == "B101"
    assert diag["line"] == 12
    assert diag["severity"] == "LOW"


def test_mypy_parse_jsonl_real_format():
    """MypyDriver maps upstream JSONL (one object per line)."""
    mod = _load_driver("cdmplugins.mypy.mypydriver", "mypy/mypydriver.py")
    driver = mod.MypyDriver(None)
    driver._fileName = "/tmp/sample.py"
    results = {"Diagnostics": []}
    stdout = (
        json.dumps(
            {
                "file": "/tmp/sample.py",
                "line": 7,
                "column": 4,
                "end_line": 7,
                "end_column": 10,
                "message": 'Module has no attribute "missing"',
                "hint": None,
                "code": "attr-defined",
                "severity": "error",
            }
        )
        + "\n"
        + json.dumps(
            {
                "file": "/tmp/other.py",
                "line": 1,
                "column": 1,
                "message": "unrelated",
                "code": "name-defined",
                "severity": "error",
            }
        )
        + "\n"
    )
    driver.parseOutput(stdout, "", results)
    assert len(results["Diagnostics"]) == 1
    diag = results["Diagnostics"][0]
    assert diag["code"] == "attr-defined"
    assert diag["line"] == 7
    assert diag["column"] == 4
    assert diag["severity"] == "error"


def test_mypy_parse_legacy_files_object_compat():
    """Legacy fabricated {\"files\":...} still parses for backward compat."""
    mod = _load_driver("cdmplugins.mypy.mypydriver", "mypy/mypydriver.py")
    driver = mod.MypyDriver(None)
    driver._fileName = "/tmp/sample.py"
    results = {"Diagnostics": []}
    stdout = json.dumps(
        {
            "files": {
                "sample.py": [
                    {
                        "code": "attr-defined",
                        "message": 'Module has no attribute "missing"',
                        "line": 7,
                        "column": 4,
                    }
                ]
            }
        }
    )
    driver.parseOutput(stdout, "", results)
    assert len(results["Diagnostics"]) == 1
    assert results["Diagnostics"][0]["code"] == "attr-defined"


def test_ruff_parse_output_invalid_json():
    """Invalid JSON sets ProcessError instead of raising."""
    mod = _load_driver("cdmplugins.ruff.ruffdriver", "ruff/ruffdriver.py")
    driver = mod.RuffDriver(None)
    results = {"Diagnostics": []}
    driver.parseOutput("not-json", "", results)
    assert results["ProcessError"] == "Failed to parse ruff output"
    assert results["Diagnostics"] == []


@pytest.mark.integration
def test_mypy_jsonl_integration_subprocess(tmp_path):
    """Pinned mypy --output json produces parseable JSONL (T034)."""
    import subprocess

    sample = tmp_path / "sample.py"
    sample.write_text("x: int = 'a'\n", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "mypy", "--output", "json", "--no-error-summary", str(sample)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.stdout.strip(), proc.stderr
    mod = _load_driver("cdmplugins.mypy.mypydriver", "mypy/mypydriver.py")
    driver = mod.MypyDriver(None)
    driver._fileName = str(sample)
    results = {"Diagnostics": []}
    driver.parseOutput(proc.stdout, proc.stderr, results)
    assert results["Diagnostics"]
    assert results["Diagnostics"][0]["line"] >= 1


def test_lint_driver_start_uses_system_environment():
    """LintDriverBase inherits PATH/HOME via process_env builder."""
    mod = _load_driver("cdmplugins.mypy.mypydriver", "mypy/mypydriver.py")

    class Ide:
        project = object()

    driver = mod.MypyDriver(Ide())
    err = driver.start("/tmp/sample.py", "utf-8")
    assert err is None
    assert driver._process is not None
    assert driver._process._env is not None
    assert driver._process._env.contains("PYTHONIOENCODING")
    # Inherited from Fake systemEnvironment seeded with os.environ
    if "PATH" in os.environ:
        assert driver._process._env.contains("PATH")
