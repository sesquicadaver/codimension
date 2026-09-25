# -*- coding: utf-8 -*-
"""R279: Qt platform plugins bootstrap (xcb / empty QT_PLUGIN_PATH)."""

from __future__ import annotations

import os

import pytest

pytest.importorskip("PyQt5.QtCore")


def test_ensure_restores_library_paths_after_clear(monkeypatch) -> None:
    """Cleared libraryPaths must regain PyQt5 plugins before QApplication."""
    from PyQt5.QtCore import QCoreApplication, QLibraryInfo

    from codimension.utils.qt_bootstrap import ensure_qt_platform_plugins, pyqt5_plugins_dir

    plugins = pyqt5_plugins_dir()
    assert plugins is not None
    assert plugins == QLibraryInfo.location(QLibraryInfo.PluginsPath)

    monkeypatch.setenv("QT_PLUGIN_PATH", "")
    monkeypatch.setenv("QT_QPA_PLATFORM_PLUGIN_PATH", "")
    QCoreApplication.setLibraryPaths([])
    assert QCoreApplication.libraryPaths() == []

    restored = ensure_qt_platform_plugins()
    assert restored == plugins
    assert plugins in QCoreApplication.libraryPaths()
    assert os.environ.get("QT_PLUGIN_PATH", "").split(os.pathsep)[0] == plugins
    assert "QT_QPA_PLATFORM_PLUGIN_PATH" not in os.environ


def test_pyqt5_plugins_dir_has_platforms() -> None:
    """Vendored PyQt5 wheel must expose platforms/libqxcb (or offscreen)."""
    from codimension.utils.qt_bootstrap import pyqt5_plugins_dir

    plugins = pyqt5_plugins_dir()
    assert plugins is not None
    platforms = os.path.join(plugins, "platforms")
    assert os.path.isdir(platforms)
    so_names = {name for name in os.listdir(platforms) if name.startswith("libq")}
    assert so_names & {"libqxcb.so", "libqoffscreen.so"}
