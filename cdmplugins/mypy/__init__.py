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

"""Codimension mypy plugin implementation"""

import logging
import os.path

from packaging.version import Version
from plugins.categories.wizardiface import WizardInterface
from ui.qt import QIcon, QTabBar, QApplication, QCursor, Qt, QShortcut, QKeySequence, QAction, QMenu
from ui.mainwindowtabwidgetbase import MainWindowTabWidgetBase
from utils.fileutils import isPythonMime
from utils.pixmapcache import getIcon
from .mypydriver import MypyDriver
from .mypyresultviewer import MypyResultViewer

PLUGIN_HOME_DIR = os.path.dirname(os.path.abspath(__file__)) + os.path.sep


class MypyPlugin(WizardInterface):
    """Codimension mypy plugin."""

    def __init__(self):
        WizardInterface.__init__(self)
        self.__mypyDriver = None
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

        self.__resultViewer = MypyResultViewer(self.ide, PLUGIN_HOME_DIR)
        self.ide.sideBars['bottom'].addTab(
            self.__resultViewer, getIcon('run.png'),
            'Mypy', 'mypy', 2)
        self.ide.sideBars['bottom'].tabButton(
            'mypy', QTabBar.RightSide).resize(0, 0)

        self.__resultViewer.clear()

        self.__mypyDriver = MypyDriver(self.ide)
        self.__mypyDriver.sigFinished.connect(self.__mypyFinished)

        if self.__globalShortcut is None:
            self.__globalShortcut = QShortcut(QKeySequence('Ctrl+Shift+M'),
                                              self.ide.mainWindow, self.__run)
        else:
            self.__globalShortcut.setKey(QKeySequence('Ctrl+Shift+M'))

        for _, _, tabWidget in self.ide.editorsManager.getTextEditors():
            self.__addButton(tabWidget)

        self.ide.editorsManager.sigTextEditorTabAdded.connect(
            self.__textEditorTabAdded)
        self.ide.editorsManager.sigFileTypeChanged.connect(
            self.__fileTypeChanged)

        self.__mainMenu = QMenu('Mypy', self.ide.mainWindow)
        self.__mainMenu.setIcon(getIcon('run.png'))
        self.__mainRunAction = self.__mainMenu.addAction(
            getIcon('run.png'),
            'Run mypy\t(Ctrl+Shift+M)', self.__run)
        toolsMenu = self.ide.mainWindow.menuBar().findChild(QMenu, 'tools')
        self.__mainMenuSeparator = toolsMenu.addSeparator()
        toolsMenu.addMenu(self.__mainMenu)
        self.__mainMenu.aboutToShow.connect(self.__mainMenuAboutToShow)

    def deactivate(self):
        """Deactivates the plugin."""
        self.__globalShortcut.setKey(0)

        self.__resultViewer = None
        self.ide.sideBars['bottom'].removeTab('mypy')
        self.__mypyDriver = None

        for _, _, tabWidget in self.ide.editorsManager.getTextEditors():
            mypyAction = tabWidget.toolbar.findChild(QAction, 'mypy')
            if mypyAction is not None:
                tabWidget.toolbar.removeAction(mypyAction)
                mypyAction.deleteLater()
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
            'Run mypy\t(Ctrl+Shift+M)', self.__run)
        parentMenu.aboutToShow.connect(self.__bufferMenuAboutToShow)

    def __canRun(self, editorWidget):
        """Tells if mypy can be run for the given editor widget."""
        if self.__mypyDriver.isInProcess():
            return False, None
        if editorWidget.getType() != MainWindowTabWidgetBase.PlainTextEditor:
            return False, None
        if not isPythonMime(editorWidget.getMime()):
            return False, None
        if editorWidget.isModified():
            return False, 'Save changes before running mypy'
        if not os.path.isabs(editorWidget.getFileName()):
            return False, 'Save the file before running mypy'
        return True, None

    def __run(self):
        """Runs the mypy analysis."""
        editorWidget = self.ide.currentEditorWidget
        canRun, message = self.__canRun(editorWidget)
        if not canRun:
            if message:
                self.ide.showStatusBarMessage(message)
            return

        enc = editorWidget.getEncoding()
        message = self.__mypyDriver.start(editorWidget.getFileName(), enc)
        if message is None:
            self.__switchToRunning()
        else:
            logging.error(message)

    def __mypyFinished(self, results):
        """Mypy has finished."""
        self.__switchToIdle()
        error = results.get('ProcessError', None)
        if error:
            logging.error(error)
        else:
            self.__resultViewer.showResults(results)
            self.ide.mainWindow.activateBottomTab('mypy')

    def __switchToRunning(self):
        """Switching to the running mode."""
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        for _, _, tabWidget in self.ide.editorsManager.getTextEditors():
            mypyAction = tabWidget.toolbar.findChild(QAction, 'mypy')
            if mypyAction is not None:
                mypyAction.setEnabled(False)

    def __switchToIdle(self):
        """Switching to the idle mode."""
        QApplication.restoreOverrideCursor()
        for _, _, tabWidget in self.ide.editorsManager.getTextEditors():
            mypyAction = tabWidget.toolbar.findChild(QAction, 'mypy')
            if mypyAction is not None:
                mypyAction.setEnabled(self.__canRun(tabWidget)[0])

    def __addButton(self, tabWidget):
        """Adds a button to the editor toolbar."""
        mypyButton = QAction(getIcon('run.png'),
                             'Run mypy (Ctrl+Shift+M)', tabWidget.toolbar)
        mypyButton.setEnabled(self.__canRun(tabWidget)[0])
        mypyButton.triggered.connect(self.__run)
        mypyButton.setObjectName('mypy')

        beforeWidget = tabWidget.toolbar.findChild(QAction,
                                                  'deadCodeScriptButton')
        if beforeWidget is not None:
            tabWidget.toolbar.insertAction(beforeWidget, mypyButton)
        else:
            tabWidget.toolbar.addAction(mypyButton)
        tabWidget.getEditor().modificationChanged.connect(
            self.__modificationChanged)

    def __modificationChanged(self):
        """Triggered when editor modification state changed."""
        mypyAction = self.ide.currentEditorWidget.toolbar.findChild(QAction,
                                                                    'mypy')
        if mypyAction is not None:
            mypyAction.setEnabled(
                self.__canRun(self.ide.currentEditorWidget)[0])

    def __textEditorTabAdded(self, tabIndex):
        """Triggered when a new tab is added."""
        del tabIndex
        self.__addButton(self.ide.currentEditorWidget)

    def __fileTypeChanged(self, shortFileName, uuid, mime):
        """Triggered when a file changed its type."""
        del shortFileName, uuid, mime
        mypyAction = self.ide.currentEditorWidget.toolbar.findChild(QAction,
                                                                    'mypy')
        if mypyAction is not None:
            mypyAction.setEnabled(
                self.__canRun(self.ide.currentEditorWidget)[0])

    def __bufferMenuAboutToShow(self):
        """The buffer context menu is about to show."""
        self.__bufferRunAction.setEnabled(
            self.__canRun(self.ide.currentEditorWidget)[0])

    def __mainMenuAboutToShow(self):
        """The main menu is about to show."""
        self.__mainRunAction.setEnabled(
            self.__canRun(self.ide.currentEditorWidget)[0])
