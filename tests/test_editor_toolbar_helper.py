# -*- coding: utf-8 -*-
"""Editor toolbar helper rejects WelcomeWidget / non-editors."""

from __future__ import annotations

from ui.mainwindowtabwidgetbase import MainWindowTabWidgetBase

from cdmplugins.editor_toolbar import plain_text_editor_with_toolbar, toolbar_action


class _FakeWelcome:
    def getType(self):
        return MainWindowTabWidgetBase.HTMLViewer


class _FakeEditor:
    def __init__(self):
        self.toolbar = object()

    def getType(self):
        return MainWindowTabWidgetBase.PlainTextEditor


class _FakeTabs:
    def __init__(self, widgets):
        self._widgets = widgets

    def widget(self, index):
        return self._widgets[index]


def test_welcome_current_without_tab_index_returns_none() -> None:
    assert plain_text_editor_with_toolbar(None, current_widget=_FakeWelcome()) is None


def test_prefers_tab_index_over_stale_welcome_current() -> None:
    editor = _FakeEditor()
    tabs = _FakeTabs([editor, _FakeWelcome()])
    got = plain_text_editor_with_toolbar(tabs, 0, current_widget=_FakeWelcome())
    assert got is editor


def test_stale_current_when_tab_missing_toolbar() -> None:
    class _NoToolbar:
        def getType(self):
            return MainWindowTabWidgetBase.PlainTextEditor

    assert plain_text_editor_with_toolbar(None, current_widget=_NoToolbar()) is None


def test_toolbar_action_none_without_toolbar() -> None:
    assert toolbar_action(_FakeWelcome(), "coverage") is None
