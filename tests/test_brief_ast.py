# -*- coding: utf-8 -*-
"""Tests for brief module info filename propagation."""

import ast
from unittest.mock import patch

from parsers.brief_ast import getBriefModuleInfoFromMemory


def test_get_brief_module_info_from_memory_passes_filename_to_ast_parse(tmp_path):
    """ast.parse must receive the real file path, not <string>."""
    file_path = tmp_path / "sample.py"
    content = "x = 1\n"
    file_path.write_text(content, encoding="utf-8")

    with patch.object(ast, "parse", wraps=ast.parse) as mock_parse:
        getBriefModuleInfoFromMemory(content, str(file_path))

    mock_parse.assert_called_once()
    assert mock_parse.call_args.args[1] == str(file_path)
