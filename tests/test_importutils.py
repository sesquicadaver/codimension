# -*- coding: utf-8 -*-
"""Tests for import resolution helper functions."""

import importlib.util
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UTILS_DIR = os.path.join(ROOT, "codimension", "utils")
PARSERS_DIR = os.path.join(ROOT, "codimension", "parsers")


def _load_importutils():
    """Load importutils without the full IDE dependency chain."""
    parsers_pkg = types.ModuleType("parsers")
    parsers_pkg.__path__ = [PARSERS_DIR]
    sys.modules["parsers"] = parsers_pkg

    spec = importlib.util.spec_from_file_location(
        "parsers.brief_ast",
        os.path.join(PARSERS_DIR, "brief_ast.py"),
    )
    brief_ast = importlib.util.module_from_spec(spec)
    sys.modules["parsers.brief_ast"] = brief_ast
    spec.loader.exec_module(brief_ast)
    sys.modules["cdmpyparser"] = brief_ast

    ui_pkg = types.ModuleType("ui")
    sys.modules["ui"] = ui_pkg
    qt_mod = types.ModuleType("ui.qt")
    qt_mod.QApplication = type("QApplication", (), {"processEvents": staticmethod(lambda: None)})
    sys.modules["ui.qt"] = qt_mod

    utils_pkg = types.ModuleType("utils")
    utils_pkg.__path__ = [UTILS_DIR]
    sys.modules["utils"] = utils_pkg

    fileutils = types.ModuleType("utils.fileutils")
    fileutils.isPythonFile = lambda path: str(path).endswith(".py")
    sys.modules["utils.fileutils"] = fileutils

    globals_mod = types.ModuleType("utils.globals")

    class _GlobalData:
        originalSysPath = []

    globals_mod.GlobalData = _GlobalData
    sys.modules["utils.globals"] = globals_mod

    run_mod = types.ModuleType("utils.run")
    run_mod.getProjectPythonPath = lambda _project: None
    run_mod.getVenvSitePackages = lambda _python: None
    sys.modules["utils.run"] = run_mod

    spec = importlib.util.spec_from_file_location(
        "utils.importutils",
        os.path.join(UTILS_DIR, "importutils.py"),
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["utils.importutils"] = module
    spec.loader.exec_module(module)
    return module


_importutils = _load_importutils()
getUnresolvedPackageNames = _importutils.getUnresolvedPackageNames
getRequirementsHint = _importutils.getRequirementsHint


def test_get_unresolved_package_names_skips_relative_imports():
    """Relative imports must not produce empty pip package hints."""
    errors = [
        "Could not resolve 'from .foo import ...' at line 10",
        "Could not resolve 'from . import x' at line 11",
    ]
    assert getUnresolvedPackageNames(errors) == set()


def test_get_unresolved_package_names_collects_third_party():
    """Absolute third-party imports are collected for pip hints."""
    errors = [
        "Could not resolve 'from numpy import array' at line 2",
        "Could not resolve 'import requests' at line 3",
    ]
    assert getUnresolvedPackageNames(errors) == {"numpy", "requests"}


def test_get_requirements_hint_returns_none_for_relative_only_errors(tmp_path):
    """No misleading pip hint when only relative imports failed."""
    errors = ["Could not resolve 'from .pkg import x' at line 1"]
    unresolved = getUnresolvedPackageNames(errors)
    assert getRequirementsHint(str(tmp_path), unresolved) is None
