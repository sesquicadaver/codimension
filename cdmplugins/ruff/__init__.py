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

"""Codimension ruff plugin implementation"""

import logging
import os.path

from packaging.version import Version
from plugins.categories.wizardiface import WizardInterface
from ui.mainwindowtabwidgetbase import MainWindowTabWidgetBase
from ui.qt import QAction, QApplication, QCursor, QKeySequence, QMenu, QShortcut, Qt, QTabBar
from utils.fileutils import isPythonMime
from utils.pixmapcache import getIcon

from .ruffdriver import RuffDriver
from .ruffresultviewer import RuffResultViewer

PLUGIN_HOME_DIR = os.path.dirname(os.path.abspath(__file__)) + os.path.sep


class RuffPlugin(WizardInterface):
    """Codimension ruff plugin."""

    def __init__(self):
        WizardInterface.__init__(self)
        self.__ruffDriver = None
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

        self.__resultViewer = RuffResultViewer(self.ide, PLUGIN_HOME_DIR)
        self.ide.sideBars["bottom"].addTab(self.__resultViewer, getIcon("run.png"), "Ruff", "ruff", 2)
        self.ide.sideBars["bottom"].tabButton("ruff", QTabBar.RightSide).resize(0, 0)

        self.__resultViewer.clear()

        self.__ruffDriver = RuffDriver(self.ide)
        self.__ruffDriver.sigFinished.connect(self.__ruffFinished)

        if self.__globalShortcut is None:
            self.__globalShortcut = QShortcut(QKeySequence("Ctrl+Shift+R"), self.ide.mainWindow, self.__run)
        else:
            self.__globalShortcut.setKey(QKeySequence("Ctrl+Shift+R"))

        for _, _, tabWidget in self.ide.editorsManager.getTextEditors():
            self.__addButton(tabWidget)

        self.ide.editorsManager.sigTextEditorTabAdded.connect(self.__textEditorTabAdded)
        self.ide.editorsManager.sigFileTypeChanged.connect(self.__fileTypeChanged)

        self.__mainMenu = QMenu("Ruff", self.ide.mainWindow)
        self.__mainMenu.setIcon(getIcon("run.png"))
        self.__mainRunAction = self.__mainMenu.addAction(getIcon("run.png"), "Run ruff\t(Ctrl+Shift+R)", self.__run)
        toolsMenu = self.ide.mainWindow.menuBar().findChild(QMenu, "tools")
        self.__mainMenuSeparator = toolsMenu.addSeparator()
        toolsMenu.addMenu(self.__mainMenu)
        self.__mainMenu.aboutToShow.connect(self.__mainMenuAboutToShow)

    def deactivate(self):
        """Deactivates the plugin."""
        if self.__globalShortcut is not None:
            self.__globalShortcut.setKey(0)
            self.__globalShortcut = None

        self.__resultViewer = None
        self.ide.sideBars["bottom"].removeTab("ruff")
        self.__ruffDriver = None

        for _, _, tabWidget in self.ide.editorsManager.getTextEditors():
            ruffAction = tabWidget.toolbar.findChild(QAction, "ruff")
            if ruffAction is not None:
                tabWidget.toolbar.removeAction(ruffAction)
                ruffAction.deleteLater()
                tabWidget.getEditor().modificationChanged.disconnect(self.__modificationChanged)

        self.ide.editorsManager.sigTextEditorTabAdded.disconnect(self.__textEditorTabAdded)
        self.ide.editorsManager.sigFileTypeChanged.disconnect(self.__fileTypeChanged)

        if self.__mainRunAction is not None:
            self.__mainRunAction.deleteLater()
            self.__mainRunAction = None
        if self.__mainMenu is not None:
            self.__mainMenu.deleteLater()
            self.__mainMenu = None
        if self.__mainMenuSeparator is not None:
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
        self.__bufferRunAction = parentMenu.addAction(getIcon("run.png"), "Run ruff\t(Ctrl+Shift+R)", self.__run)
        parentMenu.aboutToShow.connect(self.__bufferMenuAboutToShow)

    def getConfigFunction(self):
        """Return config dialog for extra ruff arguments."""
        return self.__configure

    def __configure(self):
        """Open Ruff configuration dialog."""
        from ui.qt import QDialog

        from .ruffconfig import RuffConfigDialog, save_extra_args

        dlg = RuffConfigDialog(self.ide.mainWindow)
        if dlg.exec_() == QDialog.Accepted:
            save_extra_args(dlg.get_extra_args())

    def __canRun(self, editorWidget):
        """Tells if ruff can be run for the given editor widget."""
        if self.__ruffDriver is None or self.__ruffDriver.isInProcess():
            return False, None
        if editorWidget.getType() != MainWindowTabWidgetBase.PlainTextEditor:
            return False, None
        if not isPythonMime(editorWidget.getMime()):
            return False, None
        if editorWidget.isModified():
            return False, "Save changes before running ruff"
        if not os.path.isabs(editorWidget.getFileName()):
            return False, "Save the file before running ruff"
        return True, None

    def __run(self):
        """Runs the ruff analysis."""
        editorWidget = self.ide.currentEditorWidget
        canRun, message = self.__canRun(editorWidget)
        if not canRun:
            if message:
                self.ide.showStatusBarMessage(message)
            return

        enc = editorWidget.getEncoding()
        if self.__ruffDriver is None:
            return
        message = self.__ruffDriver.start(editorWidget.getFileName(), enc)
        if message is None:
            self.__switchToRunning()
        else:
            logging.error(message)

    def __ruffFinished(self, results):
        """Ruff has finished."""
        self.__switchToIdle()
        error = results.get("ProcessError", None)
        if error:
            logging.error(error)
        elif self.__resultViewer is not None:
            self.__resultViewer.showResults(results)
            self.ide.mainWindow.activateBottomTab("ruff")

    def __switchToRunning(self):
        """Switching to the running mode."""
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        for _, _, tabWidget in self.ide.editorsManager.getTextEditors():
            ruffAction = tabWidget.toolbar.findChild(QAction, "ruff")
            if ruffAction is not None:
                ruffAction.setEnabled(False)

    def __switchToIdle(self):
        """Switching to the idle mode."""
        QApplication.restoreOverrideCursor()
        for _, _, tabWidget in self.ide.editorsManager.getTextEditors():
            ruffAction = tabWidget.toolbar.findChild(QAction, "ruff")
            if ruffAction is not None:
                ruffAction.setEnabled(self.__canRun(tabWidget)[0])

    def __addButton(self, tabWidget):
        """Adds a button to the editor toolbar."""
        ruffButton = QAction(getIcon("run.png"), "Run ruff (Ctrl+Shift+R)", tabWidget.toolbar)
        ruffButton.setEnabled(self.__canRun(tabWidget)[0])
        ruffButton.triggered.connect(self.__run)
        ruffButton.setObjectName("ruff")

        beforeWidget = tabWidget.toolbar.findChild(QAction, "deadCodeScriptButton")
        if beforeWidget is not None:
            tabWidget.toolbar.insertAction(beforeWidget, ruffButton)
        else:
            tabWidget.toolbar.addAction(ruffButton)
        tabWidget.getEditor().modificationChanged.connect(self.__modificationChanged)

    def __modificationChanged(self):
        """Triggered when editor modification state changed."""
        ruffAction = self.ide.currentEditorWidget.toolbar.findChild(QAction, "ruff")
        if ruffAction is not None:
            ruffAction.setEnabled(self.__canRun(self.ide.currentEditorWidget)[0])

    def __textEditorTabAdded(self, tabIndex):
        """Triggered when a new tab is added."""
        del tabIndex
        self.__addButton(self.ide.currentEditorWidget)

    def __fileTypeChanged(self, shortFileName, uuid, mime):
        """Triggered when a file changed its type."""
        del shortFileName, uuid, mime
        ruffAction = self.ide.currentEditorWidget.toolbar.findChild(QAction, "ruff")
        if ruffAction is not None:
            ruffAction.setEnabled(self.__canRun(self.ide.currentEditorWidget)[0])

    def __bufferMenuAboutToShow(self):
        """The buffer context menu is about to show."""
        if self.__bufferRunAction is not None:
            self.__bufferRunAction.setEnabled(self.__canRun(self.ide.currentEditorWidget)[0])

    def __mainMenuAboutToShow(self):
        """The main menu is about to show."""
        if self.__mainRunAction is not None:
            self.__mainRunAction.setEnabled(self.__canRun(self.ide.currentEditorWidget)[0])
