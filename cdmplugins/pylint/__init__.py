# -*- coding: utf-8 -*-
#
# codimension - graphics python two-way code editor and analyzer
# Copyright (C) 2010-2019  Sergey Satskiy <sergey.satskiy@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

"""Codimension pylint plugin implementation"""


import logging
import os.path
from distutils.version import StrictVersion

from plugins.categories.wizardiface import WizardInterface
from ui.mainwindowtabwidgetbase import MainWindowTabWidgetBase
from ui.qt import QAction, QApplication, QCursor, QIcon, QKeySequence, QMenu, QShortcut, Qt, QTabBar
from utils.fileutils import isPythonMime

from cdmplugins.editor_toolbar import plain_text_editor_with_toolbar, toolbar_action

from .pylintconfigdialog import PylintPluginConfigDialog
from .pylintdriver import PylintDriver
from .pylintresultviewer import PylintResultViewer

PLUGIN_HOME_DIR = os.path.dirname(os.path.abspath(__file__)) + os.path.sep


class PylintPlugin(WizardInterface):

    """Codimension pylint plugin"""

    def __init__(self):
        WizardInterface.__init__(self)
        self.__pylintDriver = None
        self.__resultViewer = None
        self.__bufferRunAction = None
        self.__bufferGenerateAction = None
        self.__globalShortcut = None

        self.__mainMenu = None
        self.__mainMenuSeparator = None
        self.__mainRunAction = None
        self.__mainGenerateAction = None

    @staticmethod
    def isIDEVersionCompatible(ideVersion):
        """Checks if the IDE version is compatible with the plugin.

        Codimension makes this call before activating a plugin.
        The passed ideVersion is a string representing
        the current IDE version.
        True should be returned if the plugin is compatible with the IDE.
        """
        return StrictVersion(ideVersion) >= StrictVersion('4.7.1')

    def activate(self, ideSettings, ideGlobalData):
        """Activates the plugin.

        The plugin may override the method to do specific
        plugin activation handling.

        ideSettings - reference to the IDE Settings singleton
                      see codimension/src/utils/settings.py
        ideGlobalData - reference to the IDE global settings
                        see codimension/src/utils/globals.py

        Note: if overriden do not forget to call the
              base class activate()
        """
        WizardInterface.activate(self, ideSettings, ideGlobalData)

        self.__resultViewer = PylintResultViewer(self.ide, PLUGIN_HOME_DIR)
        self.ide.sideBars['bottom'].addTab(
            self.__resultViewer, QIcon(PLUGIN_HOME_DIR + 'pylint.png'),
            'Pylint', 'pylint', 2)
        self.ide.sideBars['bottom'].tabButton(
            'pylint', QTabBar.RightSide).resize(0, 0)

        # The clear call must be here, not in the results viewer __init__()
        # This is because the viewer has not been inserted into the side bar at
        # the time of __init__() so the tooltip setting does not work
        self.__resultViewer.clear()

        self.__pylintDriver = PylintDriver(self.ide)
        self.__pylintDriver.sigFinished.connect(self.__pylintFinished)

        if self.__globalShortcut is None:
            self.__globalShortcut = QShortcut(QKeySequence('Ctrl+L'),
                                              self.ide.mainWindow, self.__run)
        else:
            self.__globalShortcut.setKey('Ctrl+L')

        # Add buttons
        for _, _, tabWidget in self.ide.editorsManager.getTextEditors():
            self.__addButton(tabWidget)

        # File type changed & new tab
        self.ide.editorsManager.sigTextEditorTabAdded.connect(
            self.__textEditorTabAdded)
        self.ide.editorsManager.sigFileTypeChanged.connect(
            self.__fileTypeChanged)

        # Add main menu
        self.__mainMenu = QMenu('Pylint', self.ide.mainWindow)
        self.__mainMenu.setIcon(QIcon(PLUGIN_HOME_DIR + 'pylint.png'))
        self.__mainRunAction = self.__mainMenu.addAction(
            QIcon(PLUGIN_HOME_DIR + 'pylint.png'),
            'Run pylint\t(Ctrl+L)', self.__run)
        self.__mainGenerateAction = self.__mainMenu.addAction(
            QIcon(PLUGIN_HOME_DIR + 'generate.png'),
            'Generate/open pylintrc file', self.__generate)
        toolsMenu = self.ide.mainWindow.menuBar().findChild(QMenu, 'tools')
        self.__mainMenuSeparator = toolsMenu.addSeparator()
        toolsMenu.addMenu(self.__mainMenu)
        self.__mainMenu.aboutToShow.connect(self.__mainMenuAboutToShow)

    def deactivate(self):
        """Deactivates the plugin.

        The plugin may override the method to do specific
        plugin deactivation handling.
        Note: if overriden do not forget to call the
              base class deactivate()
        """
        self.__globalShortcut.setKey(0)

        self.__resultViewer = None
        self.ide.sideBars['bottom'].removeTab('pylint')
        self.__pylintDriver = None

        # Remove buttons
        for _, _, tabWidget in self.ide.editorsManager.getTextEditors():
            pylintAction = toolbar_action(tabWidget, 'pylint')
            if pylintAction is None:
                continue
            tabWidget.toolbar.removeAction(pylintAction)

            # deleteLater() is essential. Otherwise the button is not removed
            # really from the list of children
            pylintAction.deleteLater()

            tabWidget.getEditor().modificationChanged.disconnect(
                self.__modificationChanged)

        self.ide.editorsManager.sigTextEditorTabAdded.disconnect(
            self.__textEditorTabAdded)
        self.ide.editorsManager.sigFileTypeChanged.disconnect(
            self.__fileTypeChanged)

        # Remove main menu items
        self.__mainRunAction.deleteLater()
        self.__mainRunAction = None
        self.__mainGenerateAction.deleteLater()
        self.__mainGenerateAction = None
        self.__mainMenu.deleteLater()
        self.__mainMenu = None
        self.__mainMenuSeparator.deleteLater()
        self.__mainMenuSeparator = None

        WizardInterface.deactivate(self)

    def getConfigFunction(self):
        """Provides a plugun configuration function.

        The plugin can provide a function which will be called when the
        user requests plugin configuring.
        If a plugin does not require any config parameters then None
        should be returned.
        By default no configuring is required.
        """
        return self.configure

    def populateMainMenu(self, parentMenu):
        """Populates the main menu.

        The main menu looks as follows:
        Plugins
            - Plugin manager (fixed item)
            - Separator (fixed item)
            - <Plugin #1 name> (this is the parentMenu passed)
            ...
        If no items were populated by the plugin then there will be no
        <Plugin #N name> menu item shown.
        It is suggested to insert plugin configuration item here if so.
        """
        del parentMenu      # unused argument

    def populateFileContextMenu(self, parentMenu):
        """Populates the file context menu.

        The file context menu shown in the project viewer window will have
        an item with a plugin name and subitems which are populated here.
        If no items were populated then the plugin menu item will not be
        shown.

        When a callback is called the corresponding menu item will have
        attached data with an absolute path to the item.
        """
        del parentMenu      # unused argument

    def populateDirectoryContextMenu(self, parentMenu):
        """Populates the directory context menu.

        The directory context menu shown in the project viewer window will
        have an item with a plugin name and subitems which are populated
        here. If no items were populated then the plugin menu item will not
        be shown.

        When a callback is called the corresponding menu item will have
        attached data with an absolute path to the directory.
        """
        del parentMenu      # unused argument

    def populateBufferContextMenu(self, parentMenu):
        """Populates the editing buffer context menu.

        The buffer context menu shown for the current edited/viewed file
        will have an item with a plugin name and subitems which are
        populated here. If no items were populated then the plugin menu
        item will not be shown.

        Note: when a buffer context menu is selected by the user it always
              refers to the current widget. To get access to the current
              editing widget the plugin can use: self.ide.currentEditorWidget
              The widget could be of different types and some circumstances
              should be considered, e.g.:
              - it could be a new file which has not been saved yet
              - it could be modified
              - it could be that the disk file has already been deleted
              - etc.
              Having the current widget reference the plugin is able to
              retrieve the information it needs.
        """
        parentMenu.setIcon(QIcon(PLUGIN_HOME_DIR + 'pylint.png'))
        self.__bufferRunAction = parentMenu.addAction(
            QIcon(PLUGIN_HOME_DIR + 'pylint.png'),
            'Run pylint\t(Ctrl+L)', self.__run)
        self.__bufferGenerateAction = parentMenu.addAction(
            QIcon(PLUGIN_HOME_DIR + 'generate.png'),
            'Generate/open pylintrc file', self.__generate)
        parentMenu.aboutToShow.connect(self.__bufferMenuAboutToShow)

    def configure(self):
        """Configure dialog"""
        PylintPluginConfigDialog(PLUGIN_HOME_DIR, self.ide.mainWindow).exec_()

    def __canRun(self, editorWidget):
        """Tells if pylint can be run for the given editor widget"""
        if self.__pylintDriver.isInProcess():
            return False, None
        if editorWidget.getType() != MainWindowTabWidgetBase.PlainTextEditor:
            return False, None
        if not isPythonMime(editorWidget.getMime()):
            return False, None
        if editorWidget.isModified():
            return False, 'Save changes before running pylint'
        if not os.path.isabs(editorWidget.getFileName()):
            return False, 'The new file has never been saved yet. ' \
                          'Save it before running pylint'
        return True, None

    def __run(self):
        """Runs the pylint analysis"""
        editorWidget = self.ide.currentEditorWidget
        canRun, message = self.__canRun(editorWidget)
        if not canRun:
            if message:
                self.ide.showStatusBarMessage(message)
            return

        enc = editorWidget.getEncoding()
        message = self.__pylintDriver.start(editorWidget.getFileName(), enc)
        if message is None:
            self.__switchToRunning()
        else:
            logging.error(message)

    def __generate(self):
        """[Generates and] opens the pylintrc file"""
        editorWidget = self.ide.currentEditorWidget
        fileName = editorWidget.getFileName()
        if not os.path.isabs(fileName):
            fileName = None
        rcfile = self.__pylintDriver.getPylintrc(self.ide, fileName)
        if not rcfile:
            if fileName is None and not self.ide.project.isLoaded():
                logging.error('Cannot generate pylintrc. '
                              'The current buffer file has not been saved yet '
                              'and there is no project')
                return

            QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
            rcfile = self.__pylintDriver.generateRCFile(self.ide, fileName)
            QApplication.restoreOverrideCursor()

        if rcfile:
            if os.path.exists(rcfile):
                self.ide.mainWindow.openFile(rcfile, 0)
                return

        # It really could be only the rc generating error
        logging.error('Error generating pylintrc file ' + str(rcfile))

    def __pylintFinished(self, results):
        """Pylint has finished"""
        self.__switchToIdle()
        error = results.get('ProcessError', None)
        if error:
            logging.error(error)
        else:
            self.__resultViewer.showResults(results)
            self.ide.mainWindow.activateBottomTab('pylint')

    def __switchToRunning(self):
        """Switching to the running mode"""
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        # disable buttons
        for _, _, tabWidget in self.ide.editorsManager.getTextEditors():
            pylintAction = toolbar_action(tabWidget, 'pylint')
            if pylintAction is not None:
                pylintAction.setEnabled(False)
        # disable menu

    def __switchToIdle(self):
        """Switching to the idle mode"""
        QApplication.restoreOverrideCursor()
        # enable buttons
        for _, _, tabWidget in self.ide.editorsManager.getTextEditors():
            pylintAction = toolbar_action(tabWidget, 'pylint')
            if pylintAction is not None:
                pylintAction.setEnabled(self.__canRun(tabWidget)[0])
        # enable menu

    def __addButton(self, tabWidget):
        """Adds a button to the editor toolbar"""
        if plain_text_editor_with_toolbar(None, current_widget=tabWidget) is None:
            return
        pylintButton = QAction(QIcon(PLUGIN_HOME_DIR + 'pylint.png'),
                               'Run pylint (Ctrl+L)', tabWidget.toolbar)
        pylintButton.setEnabled(self.__canRun(tabWidget)[0])
        pylintButton.triggered.connect(self.__run)
        pylintButton.setObjectName('pylint')

        beforeWidget = tabWidget.toolbar.findChild(QAction,
                                                   'deadCodeScriptButton')
        if beforeWidget is not None:
            tabWidget.toolbar.insertAction(beforeWidget, pylintButton)
        else:
            tabWidget.toolbar.addAction(pylintButton)
        tabWidget.getEditor().modificationChanged.connect(
            self.__modificationChanged)

    def __modificationChanged(self):
        """Triggered when one of the text editors changed their mod state"""
        widget = plain_text_editor_with_toolbar(
            self.ide.editorsManager, current_widget=self.ide.currentEditorWidget)
        if widget is None:
            return
        pylintAction = toolbar_action(widget, 'pylint')
        if pylintAction is not None:
            pylintAction.setEnabled(self.__canRun(widget)[0])

    def __textEditorTabAdded(self, tabIndex):
        """Triggered when a new tab is added"""
        widget = plain_text_editor_with_toolbar(
            self.ide.editorsManager,
            tabIndex,
            current_widget=self.ide.currentEditorWidget,
        )
        if widget is not None:
            self.__addButton(widget)

    def __fileTypeChanged(self, shortFileName, uuid, mime):
        """Triggered when a file changed its type"""
        del shortFileName   # unused argument
        del uuid            # unused argument
        del mime            # unused argument

        # Import diagram / Welcome / other non-editors have no toolbar.
        widget = plain_text_editor_with_toolbar(
            self.ide.editorsManager, current_widget=self.ide.currentEditorWidget)
        if widget is None:
            return
        pylintAction = toolbar_action(widget, 'pylint')
        if pylintAction is not None:
            pylintAction.setEnabled(self.__canRun(widget)[0])

    def __bufferMenuAboutToShow(self):
        """The buffer context menu is about to show"""
        runEnable, generateState = self.__calcRunGenerateState()
        self.__bufferRunAction.setEnabled(runEnable)
        self.__bufferGenerateAction.setEnabled(generateState[0])
        self.__bufferGenerateAction.setText(generateState[1])

    def __mainMenuAboutToShow(self):
        """The main menu is about to show"""
        runEnable, generateState = self.__calcRunGenerateState()
        self.__mainRunAction.setEnabled(runEnable)
        self.__mainGenerateAction.setEnabled(generateState[0])
        self.__mainGenerateAction.setText(generateState[1])

    def __calcRunGenerateState(self):
        """Calculates the enable/disable state of the run/generate menu items"""
        editorWidget = self.ide.currentEditorWidget
        defaultGenerateText = 'Open pylintrc file'
        if editorWidget.getType() != MainWindowTabWidgetBase.PlainTextEditor:
            return False, (False, defaultGenerateText)
        if not isPythonMime(editorWidget.getMime()):
            return False, (False, defaultGenerateText)
        if self.__pylintDriver.isInProcess():
            return False, (False, defaultGenerateText)

        fileName = editorWidget.getFileName()
        if not os.path.isabs(fileName):
            fileName = None
        rcfile = self.__pylintDriver.getPylintrc(self.ide, fileName)

        if editorWidget.isModified():
            if rcfile:
                return False, (True, defaultGenerateText)
            return False, (True, 'Generate and open pylintrc file')

        # Saved python file and no pylint running
        if rcfile:
            return fileName is not None, (True, defaultGenerateText)
        return fileName is not None, (True, 'Generate and open pylintrc file')

