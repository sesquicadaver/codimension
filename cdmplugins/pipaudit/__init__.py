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

"""Codimension pip-audit plugin implementation.

Audits installed Python packages for known vulnerabilities.
Runs on the current environment (venv), not on individual files.
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
)
from utils.pixmapcache import getIcon

from .pipauditdriver import PipAuditDriver
from .pipauditresultviewer import PipAuditResultViewer

PLUGIN_HOME_DIR = os.path.dirname(os.path.abspath(__file__)) + os.path.sep


class PipAuditPlugin(WizardInterface):
    """Codimension pip-audit plugin."""

    def __init__(self):
        WizardInterface.__init__(self)
        self.__pipAuditDriver = None
        self.__resultViewer = None
        self.__bufferRunAction = None
        self.__globalShortcut = None
        self.__mainMenu = None
        self.__mainMenuSeparator = None
        self.__mainRunAction = None

    @staticmethod
    def isIDEVersionCompatible(ideVersion):
        """Checks if the IDE version is compatible with the plugin."""
        return Version(ideVersion) >= Version("4.7.1")

    def activate(self, ideSettings, ideGlobalData):
        """Activates the plugin."""
        WizardInterface.activate(self, ideSettings, ideGlobalData)

        self.__resultViewer = PipAuditResultViewer(self.ide, PLUGIN_HOME_DIR)
        self.ide.sideBars["bottom"].addTab(self.__resultViewer, getIcon("run.png"), "pip-audit", "pipaudit", 2)
        self.ide.sideBars["bottom"].tabButton("pipaudit", QTabBar.RightSide).resize(0, 0)

        self.__resultViewer.clear()

        self.__pipAuditDriver = PipAuditDriver(self.ide)
        self.__pipAuditDriver.sigFinished.connect(self.__pipAuditFinished)

        if self.__globalShortcut is None:
            self.__globalShortcut = QShortcut(QKeySequence("Ctrl+Shift+A"), self.ide.mainWindow, self.__run)
        else:
            self.__globalShortcut.setKey(QKeySequence("Ctrl+Shift+A"))

        self.__mainMenu = QMenu("pip-audit", self.ide.mainWindow)
        self.__mainMenu.setIcon(getIcon("run.png"))
        self.__mainRunAction = self.__mainMenu.addAction(
            getIcon("run.png"), "Audit dependencies\t(Ctrl+Shift+A)", self.__run
        )
        toolsMenu = self.ide.mainWindow.menuBar().findChild(QMenu, "tools")
        self.__mainMenuSeparator = toolsMenu.addSeparator()
        toolsMenu.addMenu(self.__mainMenu)
        self.__mainMenu.aboutToShow.connect(self.__mainMenuAboutToShow)

    def deactivate(self):
        """Deactivates the plugin."""
        self.__globalShortcut.setKey(0)

        self.__resultViewer = None
        self.ide.sideBars["bottom"].removeTab("pipaudit")
        self.__pipAuditDriver = None

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
            getIcon("run.png"), "Audit dependencies\t(Ctrl+Shift+A)", self.__run
        )
        parentMenu.aboutToShow.connect(self.__bufferMenuAboutToShow)

    def __canRun(self):
        """Tells if pip-audit can be run."""
        return not self.__pipAuditDriver.isInProcess()

    def __run(self):
        """Runs pip-audit."""
        if not self.__canRun():
            self.ide.showStatusBarMessage("pip-audit is already running")
            return

        workDir = None
        if self.ide.project.isLoaded():
            workDir = self.ide.project.getProjectDir()
        errMsg = self.__pipAuditDriver.start(workDir, "utf-8")
        if errMsg is None:
            self.__switchToRunning()
        else:
            logging.error(errMsg)

    def __pipAuditFinished(self, results):
        """pip-audit has finished."""
        self.__switchToIdle()
        if "ProcessError" in results:
            logging.error(results["ProcessError"])
        self.__resultViewer.showResults(results)
        self.ide.mainWindow.activateBottomTab("pipaudit")

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
        self.__bufferRunAction.setEnabled(self.__canRun())
