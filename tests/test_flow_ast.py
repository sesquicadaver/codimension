# -*- coding: utf-8 -*-
"""Tests for codimension.parsers.flow_ast (pure Python fallback parser)."""

import importlib.util
import os.path

_spec = importlib.util.spec_from_file_location(
    "flow_ast",
    os.path.join(os.path.dirname(__file__), "..", "codimension", "parsers", "flow_ast.py"),
)
_flow_ast = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_flow_ast)

getControlFlowFromMemory = _flow_ast.getControlFlowFromMemory
IMPORT_FRAGMENT = _flow_ast.IMPORT_FRAGMENT


def test_import_from_does_not_crash():
    """from module import name must parse (regression: _pos on str)."""
    source = "from os import path\n"
    cf = getControlFlowFromMemory(source)
    assert not cf.errors
    assert len(cf.nsuite) == 1
    frag = cf.nsuite[0]
    assert frag.kind == IMPORT_FRAGMENT
    assert "from os import path" in frag.getDisplayValue()
    assert frag.fromPart is not None
    assert frag.whatPart is not None


def test_plain_import():
    """Simple import statement."""
    source = "import sys\n"
    cf = getControlFlowFromMemory(source)
    assert not cf.errors
    assert len(cf.nsuite) == 1
    assert cf.nsuite[0].getDisplayValue() == "import sys"


def test_syntax_error_reported():
    """Syntax errors populate cf.errors without raising."""
    cf = getControlFlowFromMemory("def broken(\n")
    assert cf.errors


def test_docstring_frag_has_span_fields_for_flow_ui():
    """flow UI needs beginLine/body on docstring (hide-decors scroll restore)."""
    source = (
        '"""Module docstring."""\n'
        "\n"
        "def f():\n"
        '    """Function docstring."""\n'
        "    return 1\n"
    )
    cf = getControlFlowFromMemory(source)
    assert not cf.errors
    assert cf.docstring is not None
    assert cf.docstring.getDisplayValue() == "Module docstring."
    assert hasattr(cf.docstring, "beginLine")
    assert hasattr(cf.docstring, "endLine")
    assert cf.docstring.beginLine == 1
    assert cf.docstring.body.beginLine == 1
    assert cf.docstring.body.getLineRange() == (cf.docstring.beginLine, cf.docstring.endLine)

    func = cf.nsuite[0]
    assert func.docstring is not None
    assert func.docstring.getDisplayValue() == "Function docstring."
    assert func.docstring.beginLine == 4
    assert func.docstring.body.beginLine == 4
