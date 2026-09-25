# -*- coding: utf-8 -*-
#
# codimension - graphics python two-way code editor and analyzer
# Copyright (C) 2026  Codimension Team
# The license is described in the LICENSE file at the root directory.
#
# pylint: disable=C0305

"""Ensure PyQt5 Qt platform plugins are discoverable before QApplication."""

from __future__ import annotations

import os
from typing import Optional


def pyqt5_plugins_dir() -> Optional[str]:
    """Return PyQt5's ``Qt5/plugins`` directory when the platforms tree exists."""
    path: Optional[str] = None
    try:
        from PyQt5.QtCore import QLibraryInfo

        path = QLibraryInfo.location(QLibraryInfo.PluginsPath)
    except Exception:
        try:
            import PyQt5

            path = os.path.join(os.path.dirname(PyQt5.__file__), "Qt5", "plugins")
        except Exception:
            return None
    if path and os.path.isdir(os.path.join(path, "platforms")):
        return path
    return None


def ensure_qt_platform_plugins() -> Optional[str]:
    """Register PyQt5 platform plugins on the Qt library search path.

    Empty ``QT_PLUGIN_PATH`` / ``QT_QPA_PLATFORM_PLUGIN_PATH`` or a cleared
    ``QCoreApplication.libraryPaths()`` list produces::

        Could not find the Qt platform plugin "xcb" in ""

    Call this before constructing ``QApplication``.
    """
    plugins = pyqt5_plugins_dir()
    if not plugins:
        return None

    # Empty string in the environment is worse than unset for some Qt builds.
    if os.environ.get("QT_PLUGIN_PATH") == "":
        del os.environ["QT_PLUGIN_PATH"]
    if os.environ.get("QT_QPA_PLATFORM_PLUGIN_PATH") == "":
        del os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"]

    current = os.environ.get("QT_PLUGIN_PATH", "")
    parts = [part for part in current.split(os.pathsep) if part]
    if plugins not in parts:
        parts.insert(0, plugins)
        os.environ["QT_PLUGIN_PATH"] = os.pathsep.join(parts)

    try:
        from PyQt5.QtCore import QCoreApplication

        paths = [part for part in QCoreApplication.libraryPaths() if part]
        if plugins not in paths:
            QCoreApplication.setLibraryPaths([plugins] + [p for p in paths if p != plugins])
    except Exception:
        pass

    return plugins
