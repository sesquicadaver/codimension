# -*- coding: utf-8 -*-
"""Tests for AST tree scalar handling in astview."""

import importlib.util
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODMENSION_DIR = os.path.join(ROOT, "codimension")


def _load_astview():
    """Import ASTView with minimal Qt stubs."""
    ui_pkg = types.ModuleType("ui")
    ui_pkg.__path__ = [os.path.join(CODMENSION_DIR, "ui")]
    sys.modules["ui"] = ui_pkg

    delegates = types.ModuleType("ui.itemdelegates")

    class _NoOutlineHeightDelegate:
        def __init__(self, *_args, **_kwargs):
            pass

    delegates.NoOutlineHeightDelegate = _NoOutlineHeightDelegate
    sys.modules["ui.itemdelegates"] = delegates
    ui_pkg.itemdelegates = delegates

    qt_mod = types.ModuleType("ui.qt")

    class _Signal:
        def connect(self, *_args, **_kwargs):
            return None

    class _pyqtSignal:
        def __init__(self, *_args, **_kwargs):
            pass

        def connect(self, *_args, **_kwargs):
            return None

        def emit(self, *_args, **_kwargs):
            return None

    for name in (
        "QAbstractItemView",
        "QHeaderView",
        "QTreeWidget",
        "QTreeWidgetItem",
    ):
        setattr(qt_mod, name, type(name, (), {}))

    qt_mod.pyqtSignal = _pyqtSignal
    sys.modules["ui.qt"] = qt_mod
    ui_pkg.qt = qt_mod

    astutils = types.ModuleType("utils.astutils")
    astutils.parseSourceToAST = lambda source, filename: __import__("ast").parse(source, filename)
    utils_pkg = types.ModuleType("utils")
    utils_pkg.astutils = astutils
    sys.modules["utils"] = utils_pkg
    sys.modules["utils.astutils"] = astutils

    spec = importlib.util.spec_from_file_location(
        "editor.astview",
        os.path.join(CODMENSION_DIR, "editor", "astview.py"),
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["editor.astview"] = module
    spec.loader.exec_module(module)
    return module.ASTView


_ASTView = _load_astview()


def test_is_scalar_accepts_ellipsis_and_complex():
    """Constant.value may be Ellipsis or complex, not only str/int/float."""
    assert _ASTView._ASTView__isScalar(Ellipsis) is True
    assert _ASTView._ASTView__isScalar(1 + 2j) is True
    assert _ASTView._ASTView__isScalar(True) is True
