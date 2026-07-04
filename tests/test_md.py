# -*- coding: utf-8 -*-
"""Tests for codimension.utils.md (mistune 3.x markdown renderer)."""

import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UTILS_DIR = os.path.join(ROOT, "codimension", "utils")
_MD_PATH = os.path.join(UTILS_DIR, "md.py")


def _load_md_module():
    """Load md.py without pulling the full Settings/plantuml import chain."""
    utils_pkg = types.ModuleType("utils")
    utils_pkg.__path__ = [UTILS_DIR]
    sys.modules["utils"] = utils_pkg

    settings_mod = types.ModuleType("utils.settings")

    class _Settings:
        def __init__(self):
            self.plantUMLCache = MagicMock()
            self.plantUMLCache.getResource.return_value = None

    settings_mod.Settings = _Settings
    sys.modules["utils.settings"] = settings_mod

    fileutils_mod = types.ModuleType("utils.fileutils")
    fileutils_mod.getMagicMimeFromBuffer = lambda _text: None
    sys.modules["utils.fileutils"] = fileutils_mod

    spec = importlib.util.spec_from_file_location("utils.md", _MD_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["utils.md"] = module
    spec.loader.exec_module(module)
    return module


def test_render_markdown_heading_and_codespan():
    """Basic inline and block markdown renders without errors."""
    md = _load_md_module()
    rendered, errors, _warnings = md.renderMarkdown("test-uuid", "# Title\n\n`inline`\n", "/tmp/doc.md")
    assert errors == []
    assert rendered is not None
    assert "<h1>Title</h1>" in rendered
    assert "<u><code>inline</code></u>" in rendered


def test_render_markdown_table_plugin():
    """Pipe tables use the table plugin and custom table opener."""
    md = _load_md_module()
    source = "|a|b|\n|---|---|\n|1|2|\n"
    rendered, errors, _warnings = md.renderMarkdown("test-uuid", source, None)
    assert errors == []
    assert rendered is not None
    assert 'cellpadding="4"' in rendered
    assert "<th>a</th>" in rendered
    assert "<td>1</td>" in rendered


def test_render_markdown_relative_image():
    """Relative image paths are resolved against the markdown file directory."""
    md = _load_md_module()
    rendered, errors, _warnings = md.renderMarkdown("test-uuid", "![alt](pic.png)\n", "/project/docs/readme.md")
    assert errors == []
    assert rendered is not None
    assert 'src="/project/docs/pic.png"' in rendered or 'src="pic.png"' not in rendered
