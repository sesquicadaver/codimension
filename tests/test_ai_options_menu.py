# -*- coding: utf-8 -*-
"""Options menu exposes top-level AI actions (not a nested submenu)."""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_MAINMENU = _ROOT / "codimension" / "ui" / "mainmenu.py"
_WELCOME = _ROOT / "codimension" / "ui" / "welcomewidget.py"


def test_options_menu_has_top_level_ai_actions() -> None:
    text = _MAINMENU.read_text(encoding="utf-8")
    assert 'optionsMenu.addAction("Enable AI (experimental)")' in text
    assert 'optionsMenu.addAction("AI settings…"' in text
    assert 'optionsMenu.addMenu("AI")' not in text


def test_welcome_has_no_dead_codimension_org_link() -> None:
    text = _WELCOME.read_text(encoding="utf-8")
    assert "codimension.org" not in text
    assert "github.com/sesquicadaver/codimension" in text
    assert "github.com/SergeySatskiy/codimension" in text
