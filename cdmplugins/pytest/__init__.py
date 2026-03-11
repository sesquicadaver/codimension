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

"""Codimension pytest plugin implementation"""

import logging
import os.path

from packaging.version import Version
from plugins.categories.wizardiface import WizardInterface
from ui.qt import QTabBar, QApplication, QCursor, Qt, QShortcut, QKeySequence, QAction, QMenu
from ui.mainwindowtabwidgetbase import MainWindowTabWidgetBase
from utils.fileutils import isPythonMime
from utils.pixmapcache import getIcon
from .pytestdriver import PytestDriver
from .pytestresultviewer import PytestResultViewer

PLUGIN_HOME_DIR = os.path.dirname(os.path.abspath(__file__)) + os.path.sep


def _isTestFile(fileName):
    """True if the file looks like a pytest test file."""
    if not fileName:
        return False
    base = os.path.basename(fileName)
    return base.startswith('test_') or base.endswith('_test.py')


class PytestPlugin(WizardInterface):
    """Codimension pytest plugin."""

    def __init__(self):
        WizardInterface.__init__(self)
        self.__pytestDriver = None
        self.__resultViewer = None
        self.__bufferRunAction = None
        self.__globalShortcut = None
        self.__mainMenu = None
        self.__mainMenuSeparator = None
        self.__mainRunAction = None

    @staticmethod
    def isIDEVersionCompatible(ideVersion):
        """Checks if the IDE version is compatible with the plugin."""
        return Version(ideVersion) >= Version('4.7.1')

    def activate(self, ideSettings, ideGlobalData):
        """Activates the plugin."""
        WizardInterface.activate(self, ideSettings, ideGlobalData)

        self.__resultViewer = PytestResultViewer(self.ide, PLUGIN_HOME_DIR)
        self.ide.sideBars['bottom'].addTab(
            self.__resultViewer, getIcon('run.png'),
            'Pytest', 'pytest', 2)
        self.ide.sideBars['bottom'].tabButton(
            'pytest', QTabBar.RightSide).resize(0, 0)

        self.__resultViewer.clear()

        self.__pytestDriver = PytestDriver(self.ide)
        self.__pytestDriver.sigFinished.connect(self.__pytestFinished)

        if self.__globalShortcut is None:
            self.__globalShortcut = QShortcut(QKeySequence('Ctrl+Shift+T'),
                                              self.ide.mainWindow, self.__run)
        else:
            self.__globalShortcut.setKey(QKeySequence('Ctrl+Shift+T'))

        for _, _, tabWidget in self.ide.editorsManager.getTextEditors():
            self.__addButton(tabWidget)

        self.ide.editorsManager.sigTextEditorTabAdded.connect(
            self.__textEditorTabAdded)
        self.ide.editorsManager.sigFileTypeChanged.connect(
            self.__fileTypeChanged)

        self.__mainMenu = QMenu('Pytest', self.ide.mainWindow)
        self.__mainMenu.setIcon(getIcon('run.png'))
        self.__mainRunAction = self.__mainMenu.addAction(
            getIcon('run.png'),
            'Run pytest\t(Ctrl+Shift+T)', self.__run)
        toolsMenu = self.ide.mainWindow.menuBar().findChild(QMenu, 'tools')
        self.__mainMenuSeparator = toolsMenu.addSeparator()
        toolsMenu.addMenu(self.__mainMenu)
        self.__mainMenu.aboutToShow.connect(self.__mainMenuAboutToShow)

    def deactivate(self):
        """Deactivates the plugin."""
        self.__globalShortcut.setKey(0)

        self.__resultViewer = None
        self.ide.sideBars['bottom'].removeTab('pytest')
        self.__pytestDriver = None

        for _, _, tabWidget in self.ide.editorsManager.getTextEditors():
            pytestAction = tabWidget.toolbar.findChild(QAction, 'pytest')
            if pytestAction is not None:
                tabWidget.toolbar.removeAction(pytestAction)
                pytestAction.deleteLater()
                tabWidget.getEditor().modificationChanged.disconnect(
                    self.__modificationChanged)

        self.ide.editorsManager.sigTextEditorTabAdded.disconnect(
            self.__textEditorTabAdded)
        self.ide.editorsManager.sigFileTypeChanged.disconnect(
            self.__fileTypeChanged)

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
        parentMenu.setIcon(getIcon('run.png'))
        self.__bufferRunAction = parentMenu.addAction(
            getIcon('run.png'),
            'Run pytest\t(Ctrl+Shift+T)', self.__run)
        parentMenu.aboutToShow.connect(self.__bufferMenuAboutToShow)

    def __canRun(self, editorWidget):
        """Tells if pytest can be run for the given editor widget."""
        if self.__pytestDriver.isInProcess():
            return False, None
        if editorWidget.getType() != MainWindowTabWidgetBase.PlainTextEditor:
            return False, None
        if not isPythonMime(editorWidget.getMime()):
            return False, None
        if editorWidget.isModified():
            return False, 'Save changes before running pytest'
        if not os.path.isabs(editorWidget.getFileName()):
            return False, 'Save the file before running pytest'
        if not _isTestFile(editorWidget.getFileName()):
            return False, 'Open a test file (test_*.py or *_test.py)'
        return True, None

    def __run(self):
        """Runs pytest."""
        editorWidget = self.ide.currentEditorWidget
        canRun, message = self.__canRun(editorWidget)
        if not canRun:
            if message:
                self.ide.showStatusBarMessage(message)
            return

        enc = editorWidget.getEncoding()
        message = self.__pytestDriver.start(editorWidget.getFileName(), enc)
        if message is None:
            self.__switchToRunning()
        else:
            logging.error(message)

    def __pytestFinished(self, results):
        """Pytest has finished."""
        self.__switchToIdle()
        self.__resultViewer.showResults(results)
        self.ide.mainWindow.activateBottomTab('pytest')

    def __switchToRunning(self):
        """Switching to the running mode."""
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        for _, _, tabWidget in self.ide.editorsManager.getTextEditors():
            pytestAction = tabWidget.toolbar.findChild(QAction, 'pytest')
            if pytestAction is not None:
                pytestAction.setEnabled(False)

    def __switchToIdle(self):
        """Switching to the idle mode."""
        QApplication.restoreOverrideCursor()
        for _, _, tabWidget in self.ide.editorsManager.getTextEditors():
            pytestAction = tabWidget.toolbar.findChild(QAction, 'pytest')
            if pytestAction is not None:
                pytestAction.setEnabled(self.__canRun(tabWidget)[0])

    def __addButton(self, tabWidget):
        """Adds a button to the editor toolbar."""
        pytestButton = QAction(getIcon('run.png'),
                              'Run pytest (Ctrl+Shift+T)', tabWidget.toolbar)
        pytestButton.setEnabled(self.__canRun(tabWidget)[0])
        pytestButton.triggered.connect(self.__run)
        pytestButton.setObjectName('pytest')

        beforeWidget = tabWidget.toolbar.findChild(QAction,
                                                  'deadCodeScriptButton')
        if beforeWidget is not None:
            tabWidget.toolbar.insertAction(beforeWidget, pytestButton)
        else:
            tabWidget.toolbar.addAction(pytestButton)
        tabWidget.getEditor().modificationChanged.connect(
            self.__modificationChanged)

    def __modificationChanged(self):
        """Triggered when editor modification state changed."""
        pytestAction = self.ide.currentEditorWidget.toolbar.findChild(
            QAction, 'pytest')
        if pytestAction is not None:
            pytestAction.setEnabled(
                self.__canRun(self.ide.currentEditorWidget)[0])

    def __textEditorTabAdded(self, tabIndex):
        """Triggered when a new tab is added."""
        del tabIndex
        self.__addButton(self.ide.currentEditorWidget)

    def __fileTypeChanged(self, shortFileName, uuid, mime):
        """Triggered when a file changed its type."""
        del shortFileName, uuid, mime
        pytestAction = self.ide.currentEditorWidget.toolbar.findChild(
            QAction, 'pytest')
        if pytestAction is not None:
            pytestAction.setEnabled(
                self.__canRun(self.ide.currentEditorWidget)[0])

    def __bufferMenuAboutToShow(self):
        """The buffer context menu is about to show."""
        self.__bufferRunAction.setEnabled(
            self.__canRun(self.ide.currentEditorWidget)[0])

    def __mainMenuAboutToShow(self):
        """The main menu is about to show."""
        self.__mainRunAction.setEnabled(
            self.__canRun(self.ide.currentEditorWidget)[0])
