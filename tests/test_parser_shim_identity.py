# -*- coding: utf-8 -*-
"""T073: cdmpyparser/cdmcfparser shims must share one module object with package paths."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


def _purge_parser_modules() -> None:
    for name in list(sys.modules):
        if name in (
            "cdmpyparser",
            "cdmcfparser",
            "parsers",
        ) or name.startswith(
            (
                "codimension.parsers",
                "parsers.",
            )
        ):
            sys.modules.pop(name, None)


def test_brief_ast_aliases_are_identical() -> None:
    """cdmpyparser and codimension.parsers.brief_ast must be the same object when shimmed."""
    _purge_parser_modules()
    importlib.invalidate_caches()
    import codimension.parsers  # noqa: F401

    import cdmpyparser
    import codimension.parsers.brief_ast as brief_pkg

    assert sys.modules["cdmpyparser"] is sys.modules["codimension.parsers.brief_ast"]
    assert cdmpyparser is brief_pkg
    info = cdmpyparser.getBriefModuleInfoFromMemory("x = 1\n")
    assert isinstance(info, brief_pkg.BriefModuleInfo)


def test_flow_ast_aliases_are_identical() -> None:
    """cdmcfparser and codimension.parsers.flow_ast must be the same object when shimmed."""
    _purge_parser_modules()
    importlib.invalidate_caches()
    import codimension.parsers  # noqa: F401

    import cdmcfparser
    import codimension.parsers.flow_ast as flow_pkg

    assert sys.modules["cdmcfparser"] is sys.modules["codimension.parsers.flow_ast"]
    assert cdmcfparser is flow_pkg


def test_bootstrap_top_level_parsers_alias_identity() -> None:
    """IDE bootstrap inserts codimension/ on sys.path; parsers.* must alias shims."""
    _purge_parser_modules()
    importlib.invalidate_caches()
    root = Path(__file__).resolve().parents[1]
    codim_dir = str(root / "codimension")
    inserted = False
    if codim_dir not in sys.path:
        sys.path.insert(0, codim_dir)
        inserted = True
    try:
        import parsers  # noqa: F401

        import cdmcfparser
        import cdmpyparser
        import parsers.brief_ast as brief_top
        import parsers.flow_ast as flow_top

        assert cdmpyparser is brief_top
        assert cdmcfparser is flow_top
        assert sys.modules["cdmpyparser"] is sys.modules["parsers.brief_ast"]
        assert sys.modules["cdmcfparser"] is sys.modules["parsers.flow_ast"]
    finally:
        if inserted and sys.path and sys.path[0] == codim_dir:
            sys.path.pop(0)
