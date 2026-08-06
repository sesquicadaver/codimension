# -*- coding: utf-8 -*-
"""T028.1 — Flow UI ↔ span coupling smoke (unicode + match/try-star layout)."""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pytest

from tests.conformance.flow_serialize import getControlFlowFromMemory, serialize_control_flow

CASES = Path(__file__).parent / "cases"

IF_FRAGMENT = 19
MATCH_FRAGMENT = 25
CODEBLOCK_FRAGMENT = 6
TRY_STAR_FRAGMENT = 27


def _walk_frags(frag):
    yield frag
    for child in getattr(frag, "nsuite", []) or []:
        yield from _walk_frags(child)
    if getattr(frag, "kind", None) in (IF_FRAGMENT, MATCH_FRAGMENT):
        for part in getattr(frag, "parts", []) or []:
            yield from _walk_frags(part)
    else_part = getattr(frag, "elsePart", None)
    if else_part is not None:
        yield from _walk_frags(else_part)
    for ep in getattr(frag, "exceptParts", []) or []:
        yield from _walk_frags(ep)
    finally_part = getattr(frag, "finallyPart", None)
    if finally_part is not None:
        yield from _walk_frags(finally_part)


def test_unicode_abs_pos_range_matches_source_slice() -> None:
    source = (CASES / "unicode_spans.py").read_text(encoding="utf-8")
    cf = getControlFlowFromMemory(source)
    for frag in _walk_frags(cf):
        if not hasattr(frag, "getAbsPosRange"):
            continue
        begin, end = frag.getAbsPosRange()
        assert 0 <= begin <= end <= len(source)
        display = frag.getDisplayValue() if hasattr(frag, "getDisplayValue") else ""
        if display and getattr(frag, "kind", None) == CODEBLOCK_FRAGMENT:
            assert source[begin:end] == display


def test_selection_bounds_stable_after_serialize_roundtrip() -> None:
    """Selection/scroll surrogate: abs ranges stable across re-parse."""
    source = (CASES / "unicode_spans.py").read_text(encoding="utf-8")
    a = serialize_control_flow(source)
    b = serialize_control_flow(source)
    assert a == b
    for node in a["nsuite"]:
        assert node["end"] >= node["begin"]


class _PermissiveCFlowSettings:
    """Minimal settings stand-in so layout can run without IDE skin."""

    def __init__(self) -> None:
        from PyQt5.QtGui import QColor, QFont, QFontMetrics

        self.noGroup = True
        self.noComment = True
        self.hidecomments = True
        self.hidedocstrings = True
        self.hidedecors = True
        self.hideexcepts = False
        self.noDocstring = True
        self.noBlock = False
        self.noImport = False
        self.noBreak = False
        self.noContinue = False
        self.noReturn = False
        self.noRaise = False
        self.noAssert = False
        self.noSysExit = False
        self.noDecor = True
        self.noFor = False
        self.noWhile = False
        self.noWith = False
        self.noTry = False
        self.noIf = False
        self.itemID = 0
        self._color = QColor(0, 0, 0)
        self._font = QFont()
        self.monoFont = self._font
        self.monoFontMetrics = QFontMetrics(self._font)
        self.badgeFont = self._font
        self.badgeFontMetrics = QFontMetrics(self._font)

    def __getattr__(self, name: str):
        if name.endswith("Color") or name.endswith("color"):
            return self._color
        if "Font" in name:
            return self._font
        if name.endswith("Metrics"):
            return self.monoFontMetrics
        # numeric layout knobs
        return 4


def _ensure_imp_shim() -> None:
    """Install full ``imp`` compat for yapsy (load_module + PKG_DIRECTORY)."""
    try:
        from imp_compat import ensure_imp_compat
    except ImportError:
        from codimension.imp_compat import ensure_imp_compat  # type: ignore[no-redef]

    ensure_imp_compat()


def test_match_and_try_star_layout_dispatch() -> None:
    """Match/TryStar must not KeyError in VirtualCanvas.layoutSuite (T028.1 / C04).

    Import failures (except missing PyQt5) fail the test — they must not become
    ``pytest.skip`` and hide Flow UI regressions.
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _ensure_imp_shim()
    pytest.importorskip("PyQt5.QtWidgets")
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    root = str(Path(__file__).resolve().parents[2] / "codimension")
    if root not in sys.path:
        sys.path.insert(0, root)
    import parsers  # noqa: F401
    from flowui.vcanvas import VirtualCanvas

    settings = _PermissiveCFlowSettings()
    match_src = (CASES / "match_case.py").read_text(encoding="utf-8")
    cf = getControlFlowFromMemory(match_src)
    match_frags = [f for f in _walk_frags(cf) if getattr(f, "kind", None) == MATCH_FRAGMENT]
    assert match_frags, "expected Match fragment from match_case.py"

    dispatched: list[int] = []
    orig_match = VirtualCanvas._VirtualCanvas__layoutMatch
    orig_try = VirtualCanvas._VirtualCanvas__layoutTry

    def _match_probe(self, item, vacant_row, column):
        dispatched.append(int(item.kind))
        return vacant_row + 1

    def _try_probe(self, item, vacant_row, column):
        dispatched.append(int(item.kind))
        return vacant_row + 1

    VirtualCanvas._VirtualCanvas__layoutMatch = _match_probe  # type: ignore[method-assign]
    VirtualCanvas._VirtualCanvas__layoutTry = _try_probe  # type: ignore[method-assign]
    try:
        canvas = VirtualCanvas(settings, None, None, [], {}, None)
        canvas.layoutSuite(0, match_frags, column=1)
        assert MATCH_FRAGMENT in dispatched

        if not hasattr(ast, "TryStar"):
            pytest.skip("TryStar requires Python 3.11+")
        try_src = (CASES / "except_star.py").read_text(encoding="utf-8")
        cf2 = getControlFlowFromMemory(try_src)
        try_stars = [f for f in _walk_frags(cf2) if getattr(f, "kind", None) == TRY_STAR_FRAGMENT]
        assert try_stars
        canvas2 = VirtualCanvas(settings, None, None, [], {}, None)
        canvas2.layoutSuite(0, try_stars, column=1)
        assert TRY_STAR_FRAGMENT in dispatched
    finally:
        VirtualCanvas._VirtualCanvas__layoutMatch = orig_match  # type: ignore[method-assign]
        VirtualCanvas._VirtualCanvas__layoutTry = orig_try  # type: ignore[method-assign]
    assert app is not None
