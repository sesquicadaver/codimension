# -*- coding: utf-8 -*-
"""Tests for occurrences search result building.

Load search modules with stubs to avoid Qt/plantuml import chains.
"""

import importlib.util
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEARCH_DIR = os.path.join(ROOT, "codimension", "search")


def _load_occurrences_modules():
    """Import occurrencesprovider without pulling the full application stack."""
    autocomplete = types.ModuleType("autocomplete")
    completelists = types.ModuleType("autocomplete.completelists")
    completelists.getOccurrences = lambda *_args, **_kwargs: []
    autocomplete.completelists = completelists
    sys.modules["autocomplete"] = autocomplete
    sys.modules["autocomplete.completelists"] = completelists

    utils = types.ModuleType("utils")
    globals_mod = types.ModuleType("utils.globals")

    class _GlobalData:
        mainWindow = None

    globals_mod.GlobalData = _GlobalData
    utils.globals = globals_mod
    sys.modules["utils"] = utils
    sys.modules["utils.globals"] = globals_mod

    cdmpyparser = types.ModuleType("cdmpyparser")
    cdmpyparser.getBriefModuleInfoFromMemory = lambda _content: types.SimpleNamespace(docstring=None)
    sys.modules["cdmpyparser"] = cdmpyparser

    fileutils = types.ModuleType("utils.fileutils")
    fileutils.getFileContent = lambda path: open(path, encoding="utf-8").read()
    fileutils.isPythonFile = lambda path: str(path).endswith(".py")
    utils.fileutils = fileutils
    sys.modules["utils.fileutils"] = fileutils

    search_pkg = types.ModuleType("search")
    search_pkg.__path__ = [SEARCH_DIR]
    sys.modules["search"] = search_pkg

    for module_name, file_name in (
        ("search.resultprovideriface", "resultprovideriface.py"),
        ("search.searchsupport", "searchsupport.py"),
        ("search.occurrencesprovider", "occurrencesprovider.py"),
    ):
        spec = importlib.util.spec_from_file_location(
            module_name,
            os.path.join(SEARCH_DIR, file_name),
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

    return sys.modules["search.occurrencesprovider"]


_occurrencesprovider = _load_occurrences_modules()
build_occurrence_results = _occurrencesprovider.build_occurrence_results
OccurrencesSearchProvider = _occurrencesprovider.OccurrencesSearchProvider


class _FakeDefinition:
    def __init__(self, name, line, module_path):
        self.name = name
        self.line = line
        self.module_path = module_path


def test_build_occurrence_results_groups_matches(tmp_path):
    """Definitions are grouped into per-file search items."""
    file_path = tmp_path / "sample.py"
    file_path.write_text("value = 1\nprint(value)\n", encoding="utf-8")

    definitions = [
        _FakeDefinition("value", 1, str(file_path)),
        _FakeDefinition("value", 2, str(file_path)),
    ]

    items = build_occurrence_results(definitions, str(file_path), "value", lambda _path: "")

    assert len(items) == 1
    assert items[0].fileName == str(file_path)
    assert len(items[0].matches) == 2


def test_build_occurrence_results_skips_invalid_definitions(tmp_path):
    """Definitions without line or module path are ignored."""
    file_path = tmp_path / "sample.py"
    file_path.write_text("pass\n", encoding="utf-8")

    definitions = [
        _FakeDefinition("x", None, str(file_path)),
        _FakeDefinition("x", 1, None),
    ]

    items = build_occurrence_results(definitions, str(file_path), "x", lambda _path: "")

    assert items == []


def test_can_redo_requires_existing_absolute_file(tmp_path):
    """Redo is enabled only for absolute paths that exist on disk."""
    file_path = tmp_path / "sample.py"
    file_path.write_text("x = 1\n", encoding="utf-8")

    assert OccurrencesSearchProvider.canRedo(
        {"filename": str(file_path), "line": 1, "column": 0, "name": "x"}
    )
    assert not OccurrencesSearchProvider.canRedo(
        {"filename": "relative.py", "line": 1, "column": 0, "name": "x"}
    )
    assert not OccurrencesSearchProvider.canRedo(
        {"filename": str(tmp_path / "missing.py"), "line": 1, "column": 0, "name": "x"}
    )
