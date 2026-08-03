# -*- coding: utf-8 -*-
"""Regression: module-level defs inside control-flow must appear in brief model."""

from __future__ import annotations

from parsers.brief_ast import getBriefModuleInfoFromMemory


def test_brief_module_level_defs_inside_if_and_try():
    src = '''
FEATURE = True

if FEATURE:
    def create_backend():
        return 1

try:
    class OptionalAdapter:
        pass
except ImportError:
    pass
'''
    info = getBriefModuleInfoFromMemory(src)
    assert info.isOK
    func_names = {f.name for f in info.functions}
    class_names = {c.name for c in info.classes}
    assert "create_backend" in func_names
    assert "OptionalAdapter" in class_names
