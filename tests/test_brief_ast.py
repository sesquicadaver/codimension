# -*- coding: utf-8 -*-
"""Tests for brief module info filename propagation."""

import warnings

from parsers.brief_ast import getBriefModuleInfoFromMemory


def test_get_brief_module_info_from_memory_uses_filename_in_warnings(tmp_path):
    """SyntaxWarnings must reference the real file, not <string>."""
    file_path = tmp_path / "sample.py"
    file_path.write_text(("x = 1\n" * 179) + 'pat = "\\("\n', encoding="utf-8")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", SyntaxWarning)
        getBriefModuleInfoFromMemory(file_path.read_text(encoding="utf-8"), str(file_path))

    escape_warnings = [w for w in caught if issubclass(w.category, SyntaxWarning)]
    assert escape_warnings
    assert all(str(file_path) in str(w.filename) for w in escape_warnings)
