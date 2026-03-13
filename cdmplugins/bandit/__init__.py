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

"""Codimension Bandit plugin implementation.

Security static analysis for Python code.
"""

import logging
import os.path

from packaging.version import Version
from plugins.categories.wizardiface import WizardInterface
from ui.mainwindowtabwidgetbase import MainWindowTabWidgetBase
from ui.qt import (
    QAction,
    QApplication,
    QCursor,
    QKeySequence,
    QMenu,
    QShortcut,
    Qt,
    QTabBar,
)
from utils.fileutils import isPythonMime
from utils.pixmapcache import getIcon

from .banditdriver import BanditDriver
from .banditresultviewer import BanditResultViewer

PLUGIN_HOME_DIR = os.path.dirname(os.path.abspath(__file__)) + os.path.sep


class BanditPlugin(WizardInterface):
    """Codimension Bandit plugin."""

    def __init__(self):
        WizardInterface.__init__(self)
        self.__banditDriver = None
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

        self.__resultViewer = BanditResultViewer(self.ide, PLUGIN_HOME_DIR)
        self.ide.sideBars["bottom"].addTab(self.__resultViewer, getIcon("run.png"), "Bandit", "bandit", 2)
        self.ide.sideBars["bottom"].tabButton("bandit", QTabBar.RightSide).resize(0, 0)

        self.__resultViewer.clear()

        self.__banditDriver = BanditDriver(self.ide)
        self.__banditDriver.sigFinished.connect(self.__banditFinished)

        if self.__globalShortcut is None:
            self.__globalShortcut = QShortcut(QKeySequence("Ctrl+Shift+B"), self.ide.mainWindow, self.__run)
        else:
            self.__globalShortcut.setKey(QKeySequence("Ctrl+Shift+B"))

        for _, _, tabWidget in self.ide.editorsManager.getTextEditors():
            self.__addButton(tabWidget)

        self.ide.editorsManager.sigTextEditorTabAdded.connect(self.__textEditorTabAdded)
        self.ide.editorsManager.sigFileTypeChanged.connect(self.__fileTypeChanged)

        self.__mainMenu = QMenu("Bandit", self.ide.mainWindow)
        self.__mainMenu.setIcon(getIcon("run.png"))
        self.__mainRunAction = self.__mainMenu.addAction(getIcon("run.png"), "Run bandit\t(Ctrl+Shift+B)", self.__run)
        toolsMenu = self.ide.mainWindow.menuBar().findChild(QMenu, "tools")
        self.__mainMenuSeparator = toolsMenu.addSeparator()
        toolsMenu.addMenu(self.__mainMenu)
        self.__mainMenu.aboutToShow.connect(self.__mainMenuAboutToShow)

    def deactivate(self):
        """Deactivates the plugin."""
        self.__globalShortcut.setKey(0)

        self.__resultViewer = None
        self.ide.sideBars["bottom"].removeTab("bandit")
        self.__banditDriver = None

        for _, _, tabWidget in self.ide.editorsManager.getTextEditors():
            banditAction = tabWidget.toolbar.findChild(QAction, "bandit")
            if banditAction is not None:
                tabWidget.toolbar.removeAction(banditAction)
                banditAction.deleteLater()
                try:
                    tabWidget.getEditor().modificationChanged.disconnect(self.__modificationChanged)
                except TypeError:
                    pass

        self.ide.editorsManager.sigTextEditorTabAdded.disconnect(self.__textEditorTabAdded)
        self.ide.editorsManager.sigFileTypeChanged.disconnect(self.__fileTypeChanged)

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
        self.__bufferRunAction = parentMenu.addAction(getIcon("run.png"), "Run bandit\t(Ctrl+Shift+B)", self.__run)
        parentMenu.aboutToShow.connect(self.__bufferMenuAboutToShow)

    def getConfigFunction(self):
        """Return config dialog for extra bandit arguments."""
        return self.__configure

    def __configure(self):
        """Open Bandit configuration dialog."""
        from ui.qt import QDialog

        from .banditconfig import BanditConfigDialog, save_extra_args

        dlg = BanditConfigDialog(self.ide.mainWindow)
        if dlg.exec_() == QDialog.Accepted:
            save_extra_args(dlg.get_extra_args())

    def __canRun(self, editorWidget):
        """Tells if bandit can be run for the given editor widget."""
        if self.__banditDriver.isInProcess():
            return False, None
        if editorWidget.getType() != MainWindowTabWidgetBase.PlainTextEditor:
            return False, None
        if not isPythonMime(editorWidget.getMime()):
            return False, None
        if editorWidget.isModified():
            return False, "Save changes before running bandit"
        if not os.path.isabs(editorWidget.getFileName()):
            return False, "Save the file before running bandit"
        return True, None

    def __run(self):
        """Runs the bandit analysis."""
        editorWidget = self.ide.currentEditorWidget
        canRun, message = self.__canRun(editorWidget)
        if not canRun:
            if message:
                self.ide.showStatusBarMessage(message)
            return

        enc = editorWidget.getEncoding()
        errMsg = self.__banditDriver.start(editorWidget.getFileName(), enc)
        if errMsg is None:
            self.__switchToRunning()
        else:
            logging.error(errMsg)

    def __banditFinished(self, results):
        """Bandit has finished."""
        self.__switchToIdle()
        if "ProcessError" in results:
            logging.error(results["ProcessError"])
        self.__resultViewer.showResults(results)
        self.ide.mainWindow.activateBottomTab("bandit")

    def __switchToRunning(self):
        """Switching to the running mode."""
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        for _, _, tabWidget in self.ide.editorsManager.getTextEditors():
            banditAction = tabWidget.toolbar.findChild(QAction, "bandit")
            if banditAction is not None:
                banditAction.setEnabled(False)

    def __switchToIdle(self):
        """Switching to the idle mode."""
        QApplication.restoreOverrideCursor()
        for _, _, tabWidget in self.ide.editorsManager.getTextEditors():
            banditAction = tabWidget.toolbar.findChild(QAction, "bandit")
            if banditAction is not None:
                banditAction.setEnabled(self.__canRun(tabWidget)[0])

    def __addButton(self, tabWidget):
        """Adds a button to the editor toolbar."""
        banditButton = QAction(
            getIcon("run.png"),
            "Run bandit (Ctrl+Shift+B)",
            tabWidget.toolbar,
        )
        banditButton.setEnabled(self.__canRun(tabWidget)[0])
        banditButton.triggered.connect(self.__run)
        banditButton.setObjectName("bandit")

        beforeWidget = tabWidget.toolbar.findChild(QAction, "deadCodeScriptButton")
        if beforeWidget is not None:
            tabWidget.toolbar.insertAction(beforeWidget, banditButton)
        else:
            tabWidget.toolbar.addAction(banditButton)
        tabWidget.getEditor().modificationChanged.connect(self.__modificationChanged)

    def __modificationChanged(self):
        """Triggered when editor modification state changed."""
        banditAction = self.ide.currentEditorWidget.toolbar.findChild(QAction, "bandit")
        if banditAction is not None:
            banditAction.setEnabled(self.__canRun(self.ide.currentEditorWidget)[0])

    def __textEditorTabAdded(self, tabIndex):
        """Triggered when a new tab is added."""
        del tabIndex
        self.__addButton(self.ide.currentEditorWidget)

    def __fileTypeChanged(self, shortFileName, uuid, mime):
        """Triggered when a file changed its type."""
        del shortFileName, uuid, mime
        banditAction = self.ide.currentEditorWidget.toolbar.findChild(QAction, "bandit")
        if banditAction is not None:
            banditAction.setEnabled(self.__canRun(self.ide.currentEditorWidget)[0])

    def __bufferMenuAboutToShow(self):
        """The buffer context menu is about to show."""
        self.__bufferRunAction.setEnabled(self.__canRun(self.ide.currentEditorWidget)[0])

    def __mainMenuAboutToShow(self):
        """The main menu is about to show."""
        self.__mainRunAction.setEnabled(self.__canRun(self.ide.currentEditorWidget)[0])
