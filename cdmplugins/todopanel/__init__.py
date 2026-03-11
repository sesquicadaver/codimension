# -*- coding: utf-8 -*-
#
# codimension - graphics python two-way code editor and analyzer
# Copyright (C) 2025  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Codimension TODO panel plugin implementation.

Scans Python files for TODO, FIXME, XXX, HACK markers (anti-stub check).
"""

import logging
import os.path

from packaging.version import Version
from plugins.categories.wizardiface import WizardInterface
from ui.qt import (
    QApplication,
    QCursor,
    QKeySequence,
    QMenu,
    QShortcut,
    Qt,
    QTabBar,
    QTimer,
)
from utils.pixmapcache import getIcon

from .todopaneldriver import TodoPanelDriver
from .todopanelviewer import TodoPanelViewer

PLUGIN_HOME_DIR = os.path.dirname(os.path.abspath(__file__)) + os.path.sep


class TodoPanelPlugin(WizardInterface):
    """Codimension TODO panel plugin."""

    SAVE_DEBOUNCE_MS = 500
    PERIODIC_INTERVAL_MS = 30000

    def __init__(self):
        WizardInterface.__init__(self)
        self.__driver = None
        self.__viewer = None
        self.__bufferRunAction = None
        self.__globalShortcut = None
        self.__mainMenu = None
        self.__mainMenuSeparator = None
        self.__mainRunAction = None
        self.__saveDebounceTimer = None
        self.__periodicTimer = None

    @staticmethod
    def isIDEVersionCompatible(ideVersion):
        """Checks if the IDE version is compatible with the plugin."""
        return Version(ideVersion) >= Version("4.7.1")

    def activate(self, ideSettings, ideGlobalData):
        """Activates the plugin."""
        WizardInterface.activate(self, ideSettings, ideGlobalData)

        self.__viewer = TodoPanelViewer(self.ide, PLUGIN_HOME_DIR)
        self.ide.sideBars["bottom"].addTab(
            self.__viewer,
            getIcon("run.png"),
            "TODO",
            "todopanel",
            2,
        )
        self.ide.sideBars["bottom"].tabButton(
            "todopanel", QTabBar.RightSide
        ).resize(0, 0)

        self.__viewer.clear()

        self.__driver = TodoPanelDriver(self.ide)
        self.__driver.sigFinished.connect(self.__scanFinished)
        self.__viewer.setRefreshCallback(self.__run)

        if self.__globalShortcut is None:
            self.__globalShortcut = QShortcut(
                QKeySequence("Ctrl+Shift+O"), self.ide.mainWindow, self.__run
            )
        else:
            self.__globalShortcut.setKey(QKeySequence("Ctrl+Shift+O"))

        self.__mainMenu = QMenu("TODO panel", self.ide.mainWindow)
        self.__mainMenu.setIcon(getIcon("run.png"))
        self.__mainRunAction = self.__mainMenu.addAction(
            getIcon("run.png"),
            "Scan TODO/FIXME\t(Ctrl+Shift+O)",
            self.__run,
        )
        toolsMenu = self.ide.mainWindow.menuBar().findChild(QMenu, "tools")
        self.__mainMenuSeparator = toolsMenu.addSeparator()
        toolsMenu.addMenu(self.__mainMenu)
        self.__mainMenu.aboutToShow.connect(self.__mainMenuAboutToShow)

        self.ide.editorsManager.sigFileUpdated.connect(self.__onFileSaved)
        self.ide.editorsManager.sigBufferSavedAs.connect(self.__onFileSaved)

        self.__saveDebounceTimer = QTimer(self)
        self.__saveDebounceTimer.setSingleShot(True)
        self.__saveDebounceTimer.timeout.connect(self.__run)

        self.__periodicTimer = QTimer(self)
        self.__periodicTimer.timeout.connect(self.__onPeriodicRefresh)
        self.__periodicTimer.start(self.PERIODIC_INTERVAL_MS)

    def deactivate(self):
        """Deactivates the plugin."""
        self.__globalShortcut.setKey(0)

        try:
            self.ide.editorsManager.sigFileUpdated.disconnect(self.__onFileSaved)
        except TypeError:
            pass
        try:
            self.ide.editorsManager.sigBufferSavedAs.disconnect(self.__onFileSaved)
        except TypeError:
            pass

        if self.__saveDebounceTimer is not None:
            self.__saveDebounceTimer.stop()
            self.__saveDebounceTimer = None
        if self.__periodicTimer is not None:
            self.__periodicTimer.stop()
            self.__periodicTimer = None

        self.__viewer = None
        self.ide.sideBars["bottom"].removeTab("todopanel")
        self.__driver = None

        self.__mainRunAction.deleteLater()
        self.__mainRunAction = None
        self.__mainMenu.deleteLater()
        self.__mainMenu = None
        self.__mainMenuSeparator.deleteLater()
        self.__mainMenuSeparator = None

        WizardInterface.deactivate(self)

    def populateMainMenu(self, parentMenu):
        """Populates the main menu."""
        del parentMenu

    def populateFileContextMenu(self, parentMenu):
        """Populates the file context menu."""
        del parentMenu

    def populateDirectoryContextMenu(self, parentMenu):
        """Populates the directory context menu."""
        del parentMenu

    def populateBufferContextMenu(self, parentMenu):
        """Populates the buffer context menu."""
        parentMenu.setIcon(getIcon("run.png"))
        self.__bufferRunAction = parentMenu.addAction(
            getIcon("run.png"),
            "Scan TODO/FIXME\t(Ctrl+Shift+O)",
            self.__run,
        )
        parentMenu.aboutToShow.connect(self.__bufferMenuAboutToShow)

    def __canRun(self):
        """Tells if scan can be run."""
        return self.__driver is not None and not self.__driver.isInProcess()

    def __run(self):
        """Runs the TODO scan."""
        if self.__driver is None:
            return
        if not self.__canRun():
            self.ide.showStatusBarMessage("TODO scan already in progress")
            return

        errMsg = self.__driver.start()
        if errMsg is None:
            self.__switchToRunning()
        else:
            self.ide.showStatusBarMessage(errMsg)
            logging.debug("TODO panel: %s", errMsg)

    def __scanFinished(self, results):
        """Scan has finished."""
        self.__switchToIdle()
        self.__viewer.showResults(results)
        self.ide.mainWindow.activateBottomTab("todopanel")

    def __switchToRunning(self):
        """Switching to the running mode."""
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        self.__mainRunAction.setEnabled(False)

    def __switchToIdle(self):
        """Switching to the idle mode."""
        QApplication.restoreOverrideCursor()
        self.__mainRunAction.setEnabled(True)

    def __mainMenuAboutToShow(self):
        """The main menu is about to show."""
        self.__mainRunAction.setEnabled(self.__canRun())

    def __bufferMenuAboutToShow(self):
        """The buffer context menu is about to show."""
        if self.__bufferRunAction is not None:
            self.__bufferRunAction.setEnabled(self.__canRun())

    def __onFileSaved(self, fileName, uuid):
        """Triggered when a file is saved. Debounces and runs scan for .py."""
        del uuid
        if not fileName or not fileName.lower().endswith(".py"):
            return
        if self.__saveDebounceTimer is None:
            return
        self.__saveDebounceTimer.stop()
        self.__saveDebounceTimer.start(self.SAVE_DEBOUNCE_MS)

    def __onPeriodicRefresh(self):
        """Periodic timer: refresh only when panel has results and not busy."""
        if (
            self.__viewer is not None
            and self.__viewer.hasResults()
            and self.__canRun()
        ):
            self.__run()
