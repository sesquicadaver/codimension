# -*- coding: utf-8 -*-
"""Tests for cdmplugins module imports.

Per-plugin smoke tests (plan section 6.1). Verifies modules load without Qt.
"""

import pytest


def test_import_lintdriverbase():
    """LintDriverBase imports."""
    from cdmplugins.lintdriverbase import LintDriverBase

    assert LintDriverBase is not None
    assert hasattr(LintDriverBase, "sigFinished")
    assert hasattr(LintDriverBase, "buildArgs")
    assert hasattr(LintDriverBase, "parseOutput")


def test_import_ruff_driver():
    """RuffDriver imports and inherits LintDriverBase."""
    from cdmplugins.lintdriverbase import LintDriverBase
    from cdmplugins.ruff.ruffdriver import RuffDriver

    assert issubclass(RuffDriver, LintDriverBase)
    assert RuffDriver.buildArgs is not LintDriverBase.buildArgs


def test_import_bandit_driver():
    """BanditDriver imports."""
    from cdmplugins.bandit.banditdriver import BanditDriver

    assert BanditDriver is not None
    assert hasattr(BanditDriver, "buildArgs")


def test_import_mypy_driver():
    """MypyDriver imports."""
    from cdmplugins.mypy.mypydriver import MypyDriver

    assert MypyDriver is not None


def test_import_ruffformat_config():
    """RuffFormat config loads."""
    from cdmplugins.ruffformat.ruffformatconfig import loadFormatOnSave

    # Should not raise; default False
    assert loadFormatOnSave() in (True, False)


def test_import_todoscanner():
    """Todoscanner imports."""
    from cdmplugins.todopanel.todoscanner import scan_file

    assert callable(scan_file)
