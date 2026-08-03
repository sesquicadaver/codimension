# -*- coding: utf-8 -*-
#
# codimension - main window debugger session mixin (T083)
# Copyright (C) 2010-2017  Sergey Satskiy <sergey.satskiy@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Debugger session UI mixin for CodimensionMainWindow (composition/routing)."""

import logging
import os.path

from debugger.bputils import clearValidBreakpointLinesCache
from debugger.client.protocol_cdm_dbg import UNHANDLED_EXCEPTION
from debugger.modifiedunsaved import ModifiedUnsavedDialog
from debugger.server import CodimensionDebugger
from utils.diskvaluesrelay import getRunParameters
from utils.globals import GlobalData
from utils.run import getNoArgsEnvironment, parseCommandLineArguments
from utils.runmanager import getWorkingDir

from .mainwindowtabwidgetbase import MainWindowTabWidgetBase
from .qt import QApplication, QDialog, QTimer


class MainWindowDebuggerMixin:
    """Debugger session routing extracted from CodimensionMainWindow (T083)."""

    DEBUG_ACTION_GO = 1
    DEBUG_ACTION_NEXT = 2
    DEBUG_ACTION_STEP_INTO = 3
    DEBUG_ACTION_RUN_TO_LINE = 4
    DEBUG_ACTION_STEP_OUT = 5

    def __init__(self):
        """Initialize debugger session state (host sets toolbar widgets later)."""
        self.debugMode = False
        self._lastDebugFileName = None
        self._lastDebugLineNumber = None
        self._lastDebugAsException = None
        self._lastDebugAction = None
        self._previousDebugging = None

    def onDebugTab(self):
        """Triggered when debug tab is requested"""
        if not self.debugMode:
            currentWidget = self.em.currentWidget()
            self._runManager.debug(currentWidget.getFileName(), False)

    def onDebugTabDlg(self):
        """Triggered when debug tab script dialog is requested"""
        if not self.debugMode:
            currentWidget = self.em.currentWidget()
            self._runManager.debug(currentWidget.getFileName(), True)

    def onDebugProject(self, _=None):
        """Debugging is requested"""
        if not self.debugMode:
            if self._checkDebugProjectPrerequisites():
                fileName = GlobalData().project.getProjectScript()
                self._runManager.debug(fileName, False)

    def onDebugProjectDlg(self):
        """Brings up the dialog with debug script settings"""
        if not self.debugMode:
            if self._checkDebugProjectPrerequisites():
                fileName = GlobalData().project.getProjectScript()
                self._runManager.debug(fileName, True)

    def _checkDebugProjectPrerequisites(self):
        """Returns True if should continue"""
        if not self._checkProjectScriptValidity():
            return False

        modifiedFiles = self.em.getModifiedList(True)
        if len(modifiedFiles) == 0:
            return True

        dlg = ModifiedUnsavedDialog(modifiedFiles, "Save and debug")
        if dlg.exec_() != QDialog.Accepted:
            # Selected to cancel
            return False

        # Need to save the modified project files
        return self.em.saveModified(True)

    def switchDebugMode(self, newState):
        """Switches the debug mode to the desired"""
        if self.debugMode == newState:
            return

        self.debugMode = newState
        self._removeCurrentDebugLineHighlight()
        clearValidBreakpointLinesCache()

        # Satatus bar
        self.sbDebugState.setVisible(newState)
        self.sbLanguage.setVisible(not newState)
        self.sbEncoding.setVisible(not newState)
        self.sbEol.setVisible(not newState)

        # Toolbar buttons
        self._dbgStop.setVisible(newState)
        self._dbgRestart.setVisible(newState)
        self._dbgGo.setVisible(newState)
        self._dbgNext.setVisible(newState)
        self._dbgStepInto.setVisible(newState)
        self._dbgRunToLine.setVisible(newState)
        self._dbgReturn.setVisible(newState)
        self._dbgJumpToCurrent.setVisible(newState)
        self._dbgDumpSettingsAct.setVisible(newState)

        if not newState:
            self._debugStopAct.setEnabled(False)
            self._debugRestartAct.setEnabled(False)
            self._debugContinueAct.setEnabled(False)
            self._debugStepOverAct.setEnabled(False)
            self._debugStepInAct.setEnabled(False)
            self._debugStepOutAct.setEnabled(False)
            self._debugRunToCursorAct.setEnabled(False)
            self._debugJumpToCurrentAct.setEnabled(False)
            self._debugDumpSettingsAct.setEnabled(False)
            self._debugDumpSettingsEnvAct.setEnabled(False)

        self.updateRunDebugButtons()

        # Tabs at the right
        if newState:
            self._rightSideBar.setTabEnabled("debugger", True)  # vars etc.
            self.debuggerContext.clear()
            self.debuggerExceptions.clear()
            self.debuggerCallTrace.clear()
            self._rightSideBar.setTabText("exceptions", "Exceptions")
            self._rightSideBar.show()
            self._rightSideBar.setCurrentTab("debugger")
            self._rightSideBar.raise_()
            self._lastDebugAction = None
            self._debugDumpSettingsAct.setEnabled(True)
            self._debugDumpSettingsEnvAct.setEnabled(True)
        else:
            if not self._rightSideBar.isMinimized():
                if self._rightSideBar.currentTabName() == "debugger":
                    self._rightSideBar.setCurrentTab("fileoutline")
            self._rightSideBar.setTabEnabled("debugger", False)  # vars etc.

        self.debugModeChanged.emit(newState)

    def _onDebuggerStateChanged(self, newState):
        """Triggered when the debugger reported its state changed"""
        if newState != CodimensionDebugger.STATE_IN_IDE:
            self._removeCurrentDebugLineHighlight()
            self.debuggerContext.switchControl(False)
        else:
            self.debuggerContext.switchControl(True)

        if newState == CodimensionDebugger.STATE_STOPPED:
            self._dbgStop.setEnabled(False)
            self._debugStopAct.setEnabled(False)
            self._dbgRestart.setEnabled(False)
            self._debugRestartAct.setEnabled(False)
            self._setDebugControlFlowButtonsState(False)
            self.sbDebugState.setText("Debugger: stopped")
        elif newState == CodimensionDebugger.STATE_IN_IDE:
            self._dbgStop.setEnabled(True)
            self._debugStopAct.setEnabled(True)
            self._dbgRestart.setEnabled(True)
            self._debugRestartAct.setEnabled(True)
            self._setDebugControlFlowButtonsState(True)
            self.sbDebugState.setText("Debugger: idle")
        elif newState == CodimensionDebugger.STATE_IN_CLIENT:
            self._dbgStop.setEnabled(True)
            self._debugStopAct.setEnabled(True)
            self._dbgRestart.setEnabled(True)
            self._debugRestartAct.setEnabled(True)
            self._setDebugControlFlowButtonsState(False)
            self.sbDebugState.setText("Debugger: running")
        QApplication.processEvents()

    def _onDebuggerCurrentLine(self, fileName, lineNumber, isStack, asException=False):
        """Triggered when the client reported a new line"""
        del isStack  # unused argument
        self._removeCurrentDebugLineHighlight()

        self._lastDebugFileName = fileName
        self._lastDebugLineNumber = lineNumber
        self._lastDebugAsException = asException
        self._onDbgJumpToCurrent()

    def _onDebuggerClientException(self, excType, excMessage, excStackTrace, isUnhandled):
        """Debugged program exception handler"""
        self.debuggerExceptions.addException(excType, excMessage, excStackTrace)
        count = self.debuggerExceptions.getTotalClientExceptionCount()
        self._rightSideBar.setTabText("exceptions", "Exceptions (" + str(count) + ")")
        self.debuggerExceptions.setFocus()

        # The information about the exception is stored in the exception window
        # regardless whether there is a stack trace or not. So, there is no
        # need to show the exception info in the closing dialog (if this dialog
        # is required).

        if isUnhandled:
            self._rightSideBar.show()
            self._rightSideBar.setCurrentTab("exceptions")
            self._rightSideBar.raise_()

            message = "Unhandled exception"
            if not excStackTrace:
                message += ": no stack trace reported"
            message += ". The debugging session is closed"

            logging.error(message)
            QTimer.singleShot(0, self._stopOnUnhandledException)
            return

        if self.debuggerExceptions.isIgnored(str(excType)):
            # Continue the last action
            if self._lastDebugAction is None:
                self._debugger.remoteContinue()
            elif self._lastDebugAction == self.DEBUG_ACTION_GO:
                self._debugger.remoteContinue()
            elif self._lastDebugAction == self.DEBUG_ACTION_NEXT:
                self._debugger.remoteStepOver()
            elif self._lastDebugAction == self.DEBUG_ACTION_STEP_INTO:
                self._debugger.remoteStep()
            elif self._lastDebugAction == self.DEBUG_ACTION_RUN_TO_LINE:
                self._debugger.remoteContinue()
            elif self._lastDebugAction == self.DEBUG_ACTION_STEP_OUT:
                self._debugger.remoteStepOut()
            return

        # Should stop at the exception
        self._rightSideBar.show()
        self._rightSideBar.setCurrentTab("exceptions")
        self._rightSideBar.raise_()

        fileName = excStackTrace[0][0]
        lineNumber = excStackTrace[0][1]
        self._onDebuggerCurrentLine(fileName, lineNumber, False, True)
        self._debugger.remoteThreadList()

        # If a stack is explicitly requested then the only deepest frame
        # is reported. It is better to stick with the exception stack
        # for the time beeing.
        self.debuggerContext.onClientStack(excStackTrace)

        self._debugger.remoteClientVariables(1, 0)  # globals
        self._debugger.remoteClientVariables(0, 0)  # locals
        self.debuggerExceptions.setFocus()

    def _onDebuggerClientSyntaxError(self, procuuid, errMessage, fileName, lineNo, charNo):
        """Triggered when the client reported a syntax error"""
        if errMessage is None:
            message = "The program being debugged contains an unspecified syntax error."
        else:
            # Jump to the source code
            self.em.openFile(fileName, lineNo)
            editor = self.em.currentWidget().getEditor()
            editor.gotoLine(lineNo, charNo)

            message = "Syntax error: '" + errMessage + "' at line " + str(lineNo) + ", position " + str(charNo) + "."

        runParameters, _ = self._debugger.getRunDebugParameters()
        if runParameters["redirected"]:
            self._runManager.appendIDEMessage(procuuid, message)
        else:
            logging.error(message)

    def _removeCurrentDebugLineHighlight(self):
        """Removes the current debug line highlight"""
        if self._lastDebugFileName is not None:
            widget = self.em.getWidgetForFileName(self._lastDebugFileName)
            if widget is not None:
                widget.getEditor().clearCurrentDebuggerLine()
            self._lastDebugFileName = None
            self._lastDebugLineNumber = None
            self._lastDebugAsException = None

    def _setDebugControlFlowButtonsState(self, enabled):
        """Sets the control flow debug buttons state"""
        self._dbgGo.setEnabled(enabled)
        self._debugContinueAct.setEnabled(enabled)
        self._dbgNext.setEnabled(enabled)
        self._debugStepOverAct.setEnabled(enabled)
        self._dbgStepInto.setEnabled(enabled)
        self._debugStepInAct.setEnabled(enabled)
        self._dbgReturn.setEnabled(enabled)
        self._debugStepOutAct.setEnabled(enabled)
        self._dbgJumpToCurrent.setEnabled(enabled)
        self._debugJumpToCurrentAct.setEnabled(enabled)

        if enabled:
            self.setRunToLineButtonState()
        else:
            self._dbgRunToLine.setEnabled(False)
            self._debugRunToCursorAct.setEnabled(False)

    def setRunToLineButtonState(self):
        """Sets the Run To Line button state"""
        # Separate story:
        # - no run to unbreakable line
        # - no run for non-python file
        if not self.debugMode:
            self._dbgRunToLine.setEnabled(False)
            self._debugRunToCursorAct.setEnabled(False)
            return
        if not self._isPythonBuffer():
            self._dbgRunToLine.setEnabled(False)
            self._debugRunToCursorAct.setEnabled(False)
            return

        # That's for sure a python buffer, so the widget exists
        currentWidget = self.em.currentWidget()
        allowedWidgets = [MainWindowTabWidgetBase.VCSAnnotateViewer]
        if currentWidget.getType() in allowedWidgets:
            self._dbgRunToLine.setEnabled(False)
            self._debugRunToCursorAct.setEnabled(False)
            return

        enabled = currentWidget.isLineBreakable()
        self._dbgRunToLine.setEnabled(enabled)
        self._debugRunToCursorAct.setEnabled(enabled)

    def _onStopDbgSession(self):
        """Debugger stop debugging clicked"""
        self._debugger.stopDebugging()

    def _stopOnUnhandledException(self):
        """Stop debuging due to an unhandled exception"""
        self._debugger.stopDebugging(UNHANDLED_EXCEPTION)

    def _onRestartDbgSession(self):
        """Debugger restart session clicked"""
        self._previousDebugging = self._debugger.getScriptPath()
        self._onStopDbgSession()

        # The debugging session is stopped in an asynchronous way
        # and the previous session must be stopped before a new one starts
        QTimer.singleShot(100, self._onRestartSessionTimer)

    def _onRestartSessionTimer(self):
        """Timer triggered debugging session restart"""
        if self._previousDebugging is not None:
            if self._debugger.getState() == self._debugger.STATE_STOPPED:
                fileName = self._previousDebugging
                self._previousDebugging = None
                self._runManager.debug(fileName, False)
            else:
                QTimer.singleShot(100, self._onRestartSessionTimer)

    def _onDbgGo(self):
        """Debugger continue clicked"""
        self._lastDebugAction = self.DEBUG_ACTION_GO
        self._debugger.remoteContinue()

    def _onDbgNext(self):
        """Debugger step over clicked"""
        self._lastDebugAction = self.DEBUG_ACTION_NEXT
        self._debugger.remoteStepOver()

    def _onDbgStepInto(self):
        """Debugger step into clicked"""
        self._lastDebugAction = self.DEBUG_ACTION_STEP_INTO
        self._debugger.remoteStep()

    def _onDbgRunToLine(self):
        """Debugger run to cursor clicked"""
        # The run-to-line button state is set approprietly
        if not self._dbgRunToLine.isEnabled():
            return

        self._lastDebugAction = self.DEBUG_ACTION_RUN_TO_LINE
        currentWidget = self.em.currentWidget()

        self._debugger.remoteBreakpoint(currentWidget.getFileName(), currentWidget.getLine() + 1, True, None, True)
        self._debugger.remoteContinue()

    def _onDbgReturn(self):
        """Debugger step out clicked"""
        self._lastDebugAction = self.DEBUG_ACTION_STEP_OUT
        self._debugger.remoteStepOut()

    def _onDbgJumpToCurrent(self):
        """Jump to the current debug line"""
        if self._lastDebugFileName is None or self._lastDebugLineNumber is None or self._lastDebugAsException is None:
            return

        self.em.openFile(self._lastDebugFileName, self._lastDebugLineNumber)

        editor = self.em.currentWidget().getEditor()
        editor.gotoLine(self._lastDebugLineNumber)
        editor.highlightCurrentDebuggerLine(self._lastDebugLineNumber, self._lastDebugAsException)
        self.em.currentWidget().setFocus()

    def getCurrentFrameNumber(self):
        """Provides the current stack frame number"""
        return self.debuggerContext.getCurrentFrameNumber()

    def _onClientExceptionsCleared(self):
        """Triggered when the user cleared the client exceptions"""
        self._rightSideBar.setTabText("exceptions", "Exceptions")

    def _onBreakpointsModelChanged(self):
        """Triggered when something is changed in the breakpoints list"""
        enabledCount, disabledCount = self._debugger.getBreakPointModel().getCounts()
        total = enabledCount + disabledCount
        title = "Breakpoints"
        if total > 0:
            title += " (" + str(total) + ")"
        self._rightSideBar.setTabText("breakpoints", title)

    def setDebugTabAvailable(self, enabled):
        """Sets a new status of the corresponding actions.

        It needs when a tab is changed or a content has been changed.
        """
        self._tabDebugAct.setEnabled(enabled)
        self._tabDebugDlgAct.setEnabled(enabled)

        self._tabRunAct.setEnabled(enabled)
        self._tabRunDlgAct.setEnabled(enabled)

        self._tabProfileAct.setEnabled(enabled)
        self._tabProfileDlgAct.setEnabled(enabled)

        # The dead code has the same dependency as debugging
        self._tabDeadCodeAct.setEnabled(enabled)

    def _dumpDebugSettings(self, fileName, fullEnvironment):
        """Provides common settings except the environment"""
        runParameters = getRunParameters(fileName)
        debugSettings = self.settings.getDebuggerSettings()
        workingDir = getWorkingDir(fileName, runParameters)
        arguments = parseCommandLineArguments(runParameters["arguments"])
        environment = getNoArgsEnvironment(runParameters)

        env = "Environment: "
        if runParameters["envType"] == runParameters.InheritParentEnv:
            env += "inherit parent"
        elif runParameters["envType"] == runParameters.InheritParentEnvPlus:
            env += "inherit parent and add/modify"
        else:
            env += "specific"

        pathVariables = []
        container = None
        if fullEnvironment:
            container = environment
            keys = list(environment.keys())
            keys.sort()
            for key in keys:
                env += "\n    " + key + " = " + environment[key]
                if "PATH" in key:
                    pathVariables.append(key)
        else:
            if runParameters["envType"] == runParameters.InheritParentEnvPlus:
                container = runParameters["additionToParentEnv"]
                keys = list(runParameters["additionToParentEnv"].keys())
                keys.sort()
                for key in keys:
                    env += "\n    " + key + " = " + runParameters["additionToParentEnv"][key]
                    if "PATH" in key:
                        pathVariables.append(key)
            elif runParameters["envType"] == runParameters.SpecificEnvironment:
                container = runParameters["specificEnv"]
                keys = list(runParameters["specificEnv"].keys())
                keys.sort()
                for key in keys:
                    env += "\n    " + key + " = " + runParameters["specificEnv"][key]
                    if "PATH" in key:
                        pathVariables.append(key)

        if pathVariables:
            env += "\nDetected PATH-containing variables:"
            for key in pathVariables:
                env += "\n    " + key
                for item in container[key].split(":"):
                    env += "\n        " + item

        if runParameters["redirected"]:
            terminal = "IO: redirected to IDE"
        else:
            terminal = "IO: custom terminal"

        logging.info(
            "\n".join(
                [
                    "Current debug session settings",
                    "Script: " + fileName,
                    "Arguments: " + " ".join(arguments),
                    "Working directory: " + workingDir,
                    env,
                    terminal,
                    "Report exceptions: " + str(debugSettings.reportExceptions),
                    "Trace interpreter libs: " + str(debugSettings.traceInterpreter),
                    "Stop at first line: " + str(debugSettings.stopAtFirstLine),
                    "Fork without asking: " + str(debugSettings.autofork),
                    "Debug child process: " + str(debugSettings.followChild),
                ]
            )
        )

    def _onDumpDebugSettings(self, action=None):
        """Triggered when dumping visible settings was requested"""
        del action  # unused argument
        self._dumpDebugSettings(self._debugger.getScriptPath(), False)

    def _onDumpFullDebugSettings(self):
        """Triggered when dumping complete settings is requested"""
        self._dumpDebugSettings(self._debugger.getScriptPath(), True)

    def _onDumpScriptDebugSettings(self):
        """Triggered when dumping current script settings is requested"""
        if self._dumpScriptDbgSettingsAvailable():
            currentWidget = self.em.currentWidget()
            self._dumpDebugSettings(currentWidget.getFileName(), False)

    def _onDumpScriptFullDebugSettings(self):
        """Dumps current script complete settings is requested"""
        if self._dumpScriptDbgSettingsAvailable():
            currentWidget = self.em.currentWidget()
            self._dumpDebugSettings(currentWidget.getFileName(), True)

    def _onDumpProjectDebugSettings(self):
        """Dumps project script settings is requested"""
        if self._dumpProjectDbgSettingsAvailable():
            project = GlobalData().project
            self._dumpDebugSettings(project.getProjectScript(), False)

    def _onDumpProjectFullDebugSettings(self):
        """Dumps project script complete settings is requested"""
        if self._dumpProjectDbgSettingsAvailable():
            project = GlobalData().project
            self._dumpDebugSettings(project.getProjectScript(), True)

    def _dumpScriptDbgSettingsAvailable(self):
        """True if dumping dbg session settings for the script is available"""
        if not self._isPythonBuffer():
            return False
        currentWidget = self.em.currentWidget()
        if currentWidget is None:
            return False
        fileName = currentWidget.getFileName()
        if os.path.isabs(fileName) and os.path.exists(fileName):
            return True
        return False

    @staticmethod
    def _dumpProjectDbgSettingsAvailable():
        """True if dumping dbg session settings for the project is available"""
        project = GlobalData().project
        if not project.isLoaded():
            return False
        fileName = project.getProjectScript()
        if fileName is None:
            return False
        if os.path.exists(fileName) and os.path.isabs(fileName):
            return True
        return False
