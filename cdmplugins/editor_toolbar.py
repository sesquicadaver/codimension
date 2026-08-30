# -*- coding: utf-8 -*-
#
# codimension - shared helpers for editor-toolbar wizard plugins
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Resolve plain-text editor tabs that expose a toolbar.

``sigTextEditorTabAdded`` historically ignored ``tabIndex`` and used
``currentEditorWidget``, which can still be :class:`WelcomeWidget` (no
``toolbar``) when tabs are restored / after ``processEvents``. Always prefer
the widget at ``tabIndex`` and require ``PlainTextEditor``.
"""

from __future__ import annotations

from typing import Any, Optional

from ui.mainwindowtabwidgetbase import MainWindowTabWidgetBase


def plain_text_editor_with_toolbar(
    editors_manager: Any,
    tab_index: Optional[int] = None,
    *,
    current_widget: Any = None,
) -> Any | None:
    """Return a PlainTextEditor with ``toolbar``, or ``None``.

    Args:
        editors_manager: EditorsManager / QTabWidget.
        tab_index: Preferred tab index from ``sigTextEditorTabAdded``.
        current_widget: Fallback (e.g. ``ide.currentEditorWidget``) when
            ``tab_index`` is omitted.
    """
    widget = None
    if tab_index is not None and editors_manager is not None:
        try:
            widget = editors_manager.widget(int(tab_index))
        except Exception:
            widget = None
    if widget is None:
        widget = current_widget
    if widget is None:
        return None
    get_type = getattr(widget, "getType", None)
    if not callable(get_type):
        return None
    try:
        if get_type() != MainWindowTabWidgetBase.PlainTextEditor:
            return None
    except Exception:
        return None
    if not hasattr(widget, "toolbar") or widget.toolbar is None:
        return None
    return widget


def toolbar_action(widget: Any, object_name: str) -> Any | None:
    """Find a named ``QAction`` on ``widget.toolbar``, or ``None``."""
    toolbar = getattr(widget, "toolbar", None)
    if toolbar is None:
        return None
    find = getattr(toolbar, "findChild", None)
    if not callable(find):
        return None
    from ui.qt import QAction

    return find(QAction, object_name)
