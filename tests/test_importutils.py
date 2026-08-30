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
    """Load importutils without the full IDE dependency chain (Qt-free)."""
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

    utils_pkg = types.ModuleType("utils")
    utils_pkg.__path__ = [UTILS_DIR]
    sys.modules["utils"] = utils_pkg

    fileutils = types.ModuleType("utils.fileutils")
    fileutils.isPythonFile = lambda path: str(path).endswith(".py")
    sys.modules["utils.fileutils"] = fileutils

    globals_mod = types.ModuleType("utils.globals")

    class _Project:
        @staticmethod
        def isLoaded():
            return False

    class _GlobalData:
        originalSysPath = list(sys.path)
        project = _Project()

    globals_mod.GlobalData = lambda: _GlobalData()
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
buildDirModules = _importutils.buildDirModules


def test_importutils_module_has_no_ui_qt_dependency():
    """R100: importutils must not pull ui.qt (gate + load-time check)."""
    assert not hasattr(_importutils, "QApplication")
    with open(os.path.join(UTILS_DIR, "importutils.py"), encoding="utf-8") as handle:
        source = handle.read()
    assert "ui.qt" not in source
    assert "QApplication" not in source


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


def test_get_unresolved_package_names_with_file_line_prefix():
    """R177: path:line: prefixes must not break package extraction."""
    errors = [
        "/proj/a.py:2: Could not resolve 'from numpy import array' at line 2",
        "/proj/b.py:3: Could not resolve 'import requests' at line 3",
    ]
    assert getUnresolvedPackageNames(errors) == {"numpy", "requests"}


def test_get_requirements_hint_returns_none_for_relative_only_errors(tmp_path):
    """No misleading pip hint when only relative imports failed."""
    errors = ["Could not resolve 'from .pkg import x' at line 1"]
    unresolved = getUnresolvedPackageNames(errors)
    assert getRequirementsHint(str(tmp_path), unresolved) is None


def test_build_dir_modules_reports_progress_without_qt(tmp_path):
    """buildDirModules uses a callable progress hook, not Qt widgets."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "mod.py").write_text("x = 1\n", encoding="utf-8")
    messages = []
    modules = buildDirModules(str(pkg), progress_callback=messages.append)
    assert "mod" in modules
    assert messages
    assert all(isinstance(m, str) and m.startswith("Scanning ") for m in messages)


def test_resolve_frozen_stdlib_import_os(tmp_path):
    """Frozen stdlib modules (os/io on 3.11+) must resolve, not WARN."""
    resolve_imports = _importutils.resolveImports

    class _Imp:
        def __init__(self, name, line):
            self.name = name
            self.line = line
            self.what = []
            self.alias = ""

    path = str(tmp_path / "mod.py")
    (tmp_path / "mod.py").write_text("import os\nimport io\n", encoding="utf-8")
    resolved, errors = resolve_imports(path, [_Imp("os", 1), _Imp("io", 2)])
    assert not errors, errors
    names = {item[0] for item in resolved}
    assert "os" in names
    assert "io" in names


def test_import_resolution_visible_name_with_import_what():
    """getVisibleName must use ImportWhat.name (not concatenate the object)."""
    import cdmpyparser

    ImportResolution = _importutils.ImportResolution
    imp = cdmpyparser.Import("pkg", 1, 0, 0)
    what = cdmpyparser.ImportWhat("sub", 1, 5, 5)
    imp.what.append(what)
    resolution = ImportResolution(imp, 0, False, "/tmp/pkg/sub.py", None)
    assert resolution.getVisibleName() == "pkg.sub"
