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

"""Codimension ruff format plugin implementation.

Formats Python code with ruff format. Result shown in status bar only.
Supports format-on-save via config.
"""

import logging
import os.path
import subprocess

from packaging.version import Version
from plugins.categories.wizardiface import WizardInterface
from ui.mainwindowtabwidgetbase import MainWindowTabWidgetBase
from ui.qt import (
    QAction,
    QApplication,
    QCursor,
    QDialog,
    QKeySequence,
    QMenu,
    QShortcut,
    Qt,
)
from utils.fileutils import isPythonMime
from utils.globals import GlobalData
from utils.pixmapcache import getIcon
from utils.run import getProjectPythonPath

from .ruffformatconfig import loadFormatOnSave, saveFormatOnSave
from .ruffformatdriver import RuffFormatDriver


class RuffFormatPlugin(WizardInterface):
    """Codimension ruff format plugin."""

    def __init__(self):
        WizardInterface.__init__(self)
        self.__formatDriver = None
        self.__bufferRunAction = None
        self.__globalShortcut = None
        self.__mainMenu = None
        self.__mainMenuSeparator = None
        self.__mainRunAction = None
        self.__formatOnSave = False
        self.__afterSaveCallback = None

    @staticmethod
    def isIDEVersionCompatible(ideVersion):
        """Checks if the IDE version is compatible with the plugin."""
        return Version(ideVersion) >= Version("4.7.1")

    def activate(self, ideSettings, ideGlobalData):
        """Activates the plugin."""
        WizardInterface.activate(self, ideSettings, ideGlobalData)

        self.__formatOnSave = loadFormatOnSave()
        self.__formatDriver = RuffFormatDriver(self.ide)
        self.__formatDriver.sigFinished.connect(self.__formatFinished)

        if self.__formatOnSave:
            self.__afterSaveCallback = self.__onAfterSave
            if self.__afterSaveCallback not in GlobalData().afterSaveCallbacks:
                GlobalData().afterSaveCallbacks.append(self.__afterSaveCallback)

        if self.__globalShortcut is None:
            self.__globalShortcut = QShortcut(QKeySequence("Ctrl+Shift+F"), self.ide.mainWindow, self.__run)
        else:
            self.__globalShortcut.setKey(QKeySequence("Ctrl+Shift+F"))

        for _, _, tabWidget in self.ide.editorsManager.getTextEditors():
            self.__addButton(tabWidget)

        self.ide.editorsManager.sigTextEditorTabAdded.connect(self.__textEditorTabAdded)
        self.ide.editorsManager.sigFileTypeChanged.connect(self.__fileTypeChanged)

        self.__mainMenu = QMenu("Ruff format", self.ide.mainWindow)
        self.__mainMenu.setIcon(getIcon("run.png"))
        self.__mainRunAction = self.__mainMenu.addAction(
            getIcon("run.png"), "Format with ruff\t(Ctrl+Shift+F)", self.__run
        )
        toolsMenu = self.ide.mainWindow.menuBar().findChild(QMenu, "tools")
        self.__mainMenuSeparator = toolsMenu.addSeparator()
        toolsMenu.addMenu(self.__mainMenu)
        self.__mainMenu.aboutToShow.connect(self.__mainMenuAboutToShow)

    def deactivate(self):
        """Deactivates the plugin."""
        self.__globalShortcut.setKey(0)

        if self.__afterSaveCallback is not None and GlobalData().afterSaveCallbacks:
            try:
                GlobalData().afterSaveCallbacks.remove(self.__afterSaveCallback)
            except ValueError:
                pass
            self.__afterSaveCallback = None

        self.__formatDriver = None

        for _, _, tabWidget in self.ide.editorsManager.getTextEditors():
            fmtAction = tabWidget.toolbar.findChild(QAction, "ruffformat")
            if fmtAction is not None:
                tabWidget.toolbar.removeAction(fmtAction)
                fmtAction.deleteLater()
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
        self.__bufferRunAction = parentMenu.addAction(
            getIcon("run.png"), "Format with ruff\t(Ctrl+Shift+F)", self.__run
        )
        parentMenu.aboutToShow.connect(self.__bufferMenuAboutToShow)

    def getConfigFunction(self):
        """Returns the config dialog for format-on-save option."""
        return self.__configure

    def __configure(self):
        """Opens the configuration dialog."""
        from .ruffformatconfig import RuffFormatConfigDialog

        dlg = RuffFormatConfigDialog(self.__formatOnSave, self.ide.mainWindow)
        if dlg.exec_() == QDialog.Accepted:
            newVal = dlg.getFormatOnSave()
            if newVal != self.__formatOnSave:
                self.__formatOnSave = newVal
                saveFormatOnSave(newVal)
                if newVal and self.__afterSaveCallback is None:
                    self.__afterSaveCallback = self.__onAfterSave
                    GlobalData().afterSaveCallbacks.append(self.__afterSaveCallback)
                elif not newVal and self.__afterSaveCallback is not None:
                    try:
                        GlobalData().afterSaveCallbacks.remove(self.__afterSaveCallback)
                    except ValueError:
                        pass
                    self.__afterSaveCallback = None

    def __onAfterSave(self, widget, fileName):
        """Called after file save. Formats Python files if format-on-save is enabled."""
        if not self.__formatOnSave:
            return
        if widget.getType() != MainWindowTabWidgetBase.PlainTextEditor:
            return
        if not isPythonMime(widget.getMime()):
            return
        if not os.path.isabs(fileName):
            return
        try:
            pythonPath = getProjectPythonPath(self.ide.project)
            result = subprocess.run(
                [pythonPath, "-m", "ruff", "format", fileName],
                capture_output=True,
                timeout=10,
                cwd=os.path.dirname(fileName),
            )
            if result.returncode == 0:
                widget.reload()
            elif result.stderr:
                logging.warning("ruff format on save: %s", result.stderr.decode("utf-8", errors="replace")[:200])
        except (subprocess.TimeoutExpired, OSError) as exc:
            logging.warning("ruff format on save failed: %s", exc)

    def __canRun(self, editorWidget):
        """Tells if format can be run for the given editor widget."""
        if self.__formatDriver.isInProcess():
            return False, None
        if editorWidget.getType() != MainWindowTabWidgetBase.PlainTextEditor:
            return False, None
        if not isPythonMime(editorWidget.getMime()):
            return False, None
        if editorWidget.isModified():
            return False, "Save changes before formatting"
        if not os.path.isabs(editorWidget.getFileName()):
            return False, "Save the file before formatting"
        return True, None

    def __run(self):
        """Runs ruff format on the current file."""
        editorWidget = self.ide.currentEditorWidget
        canRun, message = self.__canRun(editorWidget)
        if not canRun:
            if message:
                self.ide.showStatusBarMessage(message)
            return

        enc = editorWidget.getEncoding()
        errMsg = self.__formatDriver.start(editorWidget.getFileName(), enc)
        if errMsg is None:
            self.__switchToRunning()
        else:
            logging.error(errMsg)
            self.ide.showStatusBarMessage(errMsg, 5000)

    def __formatFinished(self, results):
        """Format has finished. Reload file and show status."""
        self.__switchToIdle()

        if "ProcessError" in results:
            logging.error(results["ProcessError"])
            self.ide.showStatusBarMessage(results["ProcessError"][:200], 8000)
            return

        # Reload the file to show formatted content
        try:
            editorWidget = self.ide.currentEditorWidget
            if (
                editorWidget.getType() == MainWindowTabWidgetBase.PlainTextEditor
                and editorWidget.getFileName() == results["FileName"]
            ):
                editorWidget.reload()
        except Exception as exc:
            logging.error("Failed to reload after format: %s", exc)

        self.ide.showStatusBarMessage("Formatted with ruff", 3000)

    def __switchToRunning(self):
        """Switching to the running mode."""
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        for _, _, tabWidget in self.ide.editorsManager.getTextEditors():
            fmtAction = tabWidget.toolbar.findChild(QAction, "ruffformat")
            if fmtAction is not None:
                fmtAction.setEnabled(False)

    def __switchToIdle(self):
        """Switching to the idle mode."""
        QApplication.restoreOverrideCursor()
        for _, _, tabWidget in self.ide.editorsManager.getTextEditors():
            fmtAction = tabWidget.toolbar.findChild(QAction, "ruffformat")
            if fmtAction is not None:
                fmtAction.setEnabled(self.__canRun(tabWidget)[0])

    def __addButton(self, tabWidget):
        """Adds a format button to the editor toolbar."""
        fmtButton = QAction(
            getIcon("run.png"),
            "Format with ruff (Ctrl+Shift+F)",
            tabWidget.toolbar,
        )
        fmtButton.setEnabled(self.__canRun(tabWidget)[0])
        fmtButton.triggered.connect(self.__run)
        fmtButton.setObjectName("ruffformat")

        beforeWidget = tabWidget.toolbar.findChild(QAction, "deadCodeScriptButton")
        if beforeWidget is not None:
            tabWidget.toolbar.insertAction(beforeWidget, fmtButton)
        else:
            tabWidget.toolbar.addAction(fmtButton)
        tabWidget.getEditor().modificationChanged.connect(self.__modificationChanged)

    def __modificationChanged(self):
        """Triggered when editor modification state changed."""
        fmtAction = self.ide.currentEditorWidget.toolbar.findChild(QAction, "ruffformat")
        if fmtAction is not None:
            fmtAction.setEnabled(self.__canRun(self.ide.currentEditorWidget)[0])

    def __textEditorTabAdded(self, tabIndex):
        """Triggered when a new tab is added."""
        del tabIndex
        self.__addButton(self.ide.currentEditorWidget)

    def __fileTypeChanged(self, shortFileName, uuid, mime):
        """Triggered when a file changed its type."""
        del shortFileName, uuid, mime
        fmtAction = self.ide.currentEditorWidget.toolbar.findChild(QAction, "ruffformat")
        if fmtAction is not None:
            fmtAction.setEnabled(self.__canRun(self.ide.currentEditorWidget)[0])

    def __bufferMenuAboutToShow(self):
        """The buffer context menu is about to show."""
        self.__bufferRunAction.setEnabled(self.__canRun(self.ide.currentEditorWidget)[0])

    def __mainMenuAboutToShow(self):
        """The main menu is about to show."""
        self.__mainRunAction.setEnabled(self.__canRun(self.ide.currentEditorWidget)[0])
