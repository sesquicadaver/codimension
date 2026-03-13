#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# codimension - graphics python two-way code editor and analyzer
# Copyright (C) 2010-2018  Sergey Satskiy <sergey.satskiy@gmail.com>
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

"""Codimension main Python script.

It performs necessery initialization and starts the Qt main loop.
"""

# pylint: disable=W0702
# pylint: disable=W0703
# pylint: disable=C0415
# pylint: disable=C0413

import datetime
import gc
import logging
import os
import os.path
import sys
import traceback
import warnings
from optparse import OptionParser

# Suppress pkg_resources deprecation from external plugins (cdmpylintplugin, etc.)
warnings.filterwarnings("ignore", message=".*pkg_resources.*deprecated.*", category=UserWarning)

# Workaround if link is used
sys.argv[0] = os.path.realpath(__file__)

# Make it possible to import from the subdirectories
originalSysPath = sys.path
srcDir = os.path.dirname(sys.argv[0])
if srcDir not in sys.path:
    sys.path.insert(0, srcDir)

# Use the python parser in the qutepart component
os.environ["QPART_CPARSER"] = "N"

# Python 3.12+: inject imp compatibility shim for yapsy (imp module was removed)
if sys.version_info >= (3, 12) and "imp" not in sys.modules:
    import imp_compat as _imp_shim

    sys.modules["imp"] = _imp_shim

# Inject pkg_resources compat when unavailable (setuptools 82+ removed it)
if "pkg_resources" not in sys.modules:
    try:
        import pkg_resources  # noqa: F401
    except ImportError:
        import pkg_resources_compat as _pkg_resources_shim

        sys.modules["pkg_resources"] = _pkg_resources_shim

# Install cdmpyparser/cdmcfparser fallbacks for Python 3.11+ (before any imports)
import parsers  # noqa: F401, E402
from ui.application import CodimensionApplication  # noqa: E402
from ui.qt import QMessageBox, QTimer  # noqa: E402
from ui.splashscreen import SplashScreen  # noqa: E402
from utils.config import DEFAULT_ENCODING  # noqa: E402
from utils.globals import GlobalData  # noqa: E402
from utils.project import CodimensionProject  # noqa: E402
from utils.settings import SETTINGS_DIR, Settings  # noqa: E402
from utils.skin import Skin, populateSampleSkin  # noqa: E402

# Need for the correct import resolution
GlobalData().originalSysPath = originalSysPath


try:
    import cdmverspec

    VER = cdmverspec.version
except ImportError:
    VER = "0.0.0"


class CodimensionUILauncher:
    """Wrapper class to launch Codimension"""

    def __init__(self):
        self.rootLoggingHandlers = []

        # In case of windows XServers (at least X-Win32) early usage of
        # redirected logging.something(...) leads to a silent crash. It does
        # not happen in a pure Linux environment though. So some warning
        # messages are delayed till the main application loop has started.
        self.__delayedWarnings = []

        self.__args = []
        self.__options = None
        self.__projectFile = None
        self.__splash = None

    def setupLogging(self):
        """Configures the logging module"""
        if self.__options.debug:
            logLevel = logging.DEBUG
        else:
            logLevel = logging.INFO

        # Default output stream is stderr
        logging.basicConfig(level=logLevel, format="%(levelname) -10s %(asctime)s %(message)s")

        # Memorize the root logging handlers
        self.rootLoggingHandlers = logging.root.handlers

    def isOpenable(self, fName):
        """Checks that the file can be opened"""
        # I cannot import it at the top because the fileutils want
        # to use the pixmap cache which needs the application to be
        # created, so the import is deferred
        from utils.fileutils import isFileOpenable

        if not os.path.exists(fName):
            self.__delayedWarnings.append("File does not exist: " + fName)
            return False
        if not os.path.isfile(fName):
            self.__delayedWarnings.append("The " + fName + " is not a file")
            return False
        if not isFileOpenable(fName):
            self.__delayedWarnings.append("The file " + fName + " could not be opened in Codimension")
            return False
        return True

    def processCommandLineArgs(self):
        """Checks what is in the command line"""
        # I cannot import it at the top because the fileutils want
        # to use the pixmap cache which needs the application to be
        # created, so the import is deferred
        from utils.fileutils import getFileProperties, isCDMProjectMime

        if self.__args:
            totalArgs = len(self.__args)
            goodArgs = []
            for fName in self.__args:
                if self.isOpenable(fName):
                    goodArgs.append(fName)
            self.__args = goodArgs

            if totalArgs == 1 and len(self.__args) == 1:
                mime, _, _ = getFileProperties(self.__args[0])
                if isCDMProjectMime(mime):
                    return self.__args[0]

            # Check that the is no project file because it can only come alone
            for fName in self.__args:
                mime, _, _ = getFileProperties(fName)
                if isCDMProjectMime(mime):
                    raise Exception(
                        "A Codimension project file (" + fName + ") must not come together with other files"
                    )
        return None

    def main(self):
        """The codimension driver"""
        usageMessage = "Usage: %prog [options] [project file | python files]"
        parser = OptionParser(usage=usageMessage, version="%prog " + VER)

        parser.add_option(
            "--debug",
            action="store_true",
            dest="debug",
            default=False,
            help="switch on debug and info messages (default: Off)",
        )
        parser.add_option(
            "--clean-start",
            action="store_true",
            dest="cleanStart",
            default=False,
            help="do not restore previous IDE state (default: Off)",
        )

        self.__options, self.__args = parser.parse_args()
        self.setupLogging()

        # The default exception handler can be replaced
        sys.excepthook = exceptionHook

        # Create global data singleton.
        # It's unlikely to throw any exceptions.
        globalData = GlobalData()
        globalData.version = VER

        # Loading settings - they have to be loaded before the application is
        # created. This is because the skin name is saved there.
        settings = Settings()
        populateSampleSkin()

        # Load the skin
        globalData.skin = Skin()
        globalData.skin.loadByName(settings["skin"])

        self.__delayedWarnings += settings.validateZoom(globalData.skin.minTextZoom, globalData.skin.minCFlowZoom)

        # QT on UBUNTU has a bug - the main menu bar does not generate the
        # 'aboutToHide' signal (though 'aboutToShow' is generated properly. This
        # prevents codimension working properly so the hack below disables the
        # global menu bar for codimension and makes it working properly.
        os.environ["QT_X11_NO_NATIVE_MENUBAR"] = "1"

        # Create QT application
        codimensionApp = CodimensionApplication(sys.argv, settings["style"])
        globalData.application = codimensionApp

        logging.debug("Starting codimension v.%s", VER)

        try:
            # Process command line arguments
            self.__projectFile = self.processCommandLineArgs()
        except Exception as exc:
            logging.error(str(exc))
            parser.print_help()
            return 1

        # Show splash screen
        self.__splash = SplashScreen()

        screenSize = codimensionApp.desktop().screenGeometry()
        globalData.screenWidth = screenSize.width()
        globalData.screenHeight = screenSize.height()

        self.__splash.showMessage("Importing packages...")
        from ui.mainwindow import CodimensionMainWindow

        self.__splash.showMessage("Generating main window...")
        mainWindow = CodimensionMainWindow(self.__splash, settings)
        codimensionApp.setMainWindow(mainWindow)
        globalData.mainWindow = mainWindow
        codimensionApp.lastWindowClosed.connect(codimensionApp.quit)

        mainWindow.show()
        mainWindow.restoreWindowPosition()
        mainWindow.restoreSplitterSizes()

        # Launch the user interface
        QTimer.singleShot(1, self.launchUserInterface)

        # Run the application main cycle
        retVal = codimensionApp.exec_()
        return retVal

    def launchUserInterface(self):
        """UI launchpad"""
        globalData = GlobalData()

        self.__splash.showMessage("Loading plugins...")
        globalData.pluginManager.load()

        settings = Settings()
        mainWindow = globalData.mainWindow
        mainWindow.getToolbar().setVisible(settings["showMainToolBar"])

        if not settings["showFSViewer"]:
            mainWindow.projectViewer.onShowHide(True)

        needSignal = True
        if self.__options.cleanStart:
            # Codimension will not load anything.
            pass
        elif self.__projectFile:
            self.__splash.showMessage("Loading project...")
            globalData.project.loadProject(self.__projectFile)
            needSignal = False
        elif self.__args:
            # There are arguments and they are python files
            # The project should not be loaded but the files should
            # be opened
            for fName in self.__args:
                mainWindow.openFile(os.path.abspath(fName), -1)
        elif settings["projectLoaded"]:
            # Do not auto-load last project (fast startup for large projects).
            # User can pick one from Recent Projects tab.
            pass
        else:
            mainWindow.em.restoreTabs(settings.tabStatus)

        # Signal for triggering browsers layout
        if needSignal:
            globalData.project.sigProjectChanged.emit(CodimensionProject.CompleteProject)
            # Show Recent Projects tab when starting without project
            if settings["recentProjects"]:
                mainWindow.activateRecentTab()

        # The editors positions can be restored properly only when the editors
        # have actually been drawn. Otherwise the first visible line is
        # unknown. So, I load the project first and let object browsers
        # initialize themselves and then manually call the main window handler
        # to restore the editors. The last step is to connect the signal.
        mainWindow.onProjectChanged(CodimensionProject.CompleteProject)
        globalData.project.sigProjectChanged.connect(mainWindow.onProjectChanged)

        self.__splash.finish(globalData.mainWindow)
        self.__splash = None
        del self.__splash

        for message in self.__delayedWarnings:
            logging.warning(message)

        # Some startup time objects could be collected here. In my test runs
        # there were around 700 objects.
        gc.collect()


def exceptionHook(excType, excValue, tracebackObj):
    """Catches unhandled exceptions"""
    globalData = GlobalData()

    # Keyboard interrupt is a special case
    if issubclass(excType, KeyboardInterrupt):
        if globalData.application is not None:
            globalData.application.quit()
        return

    error = "%s: %s" % (excType.__name__, excValue)
    stackTraceString = "".join(traceback.format_exception(excType, excValue, tracebackObj))

    # Save the traceback to a file explicitly together with a log window
    # content.
    excptFileName = SETTINGS_DIR + "unhandledexceptions.log"
    try:
        savedOK = True
        with open(excptFileName, "a", encoding=DEFAULT_ENCODING) as diskfile:
            diskfile.write("------ Unhandled exception report at " + str(datetime.datetime.now()) + "\n")
            diskfile.write("Traceback:\n")
            diskfile.write(stackTraceString)

            diskfile.write("Log window:\n")
            if globalData.mainWindow is not None:
                # i.e. the log window is available, save its content too
                logWindowContent = globalData.mainWindow.getLogViewerContent()
                logWindowContent = logWindowContent.strip()
                if logWindowContent:
                    diskfile.write(logWindowContent)
                    diskfile.write("\n")
                else:
                    diskfile.write("Nothing is there\n")
            else:
                diskfile.write("Has not been created yet\n")
            diskfile.write("------\n\n")
    except OSError:
        savedOK = False

    # This output will be to a console if the application has not started yet
    # or to a log window otherwise.
    logging.error("Unhandled exception is caught\n%s", stackTraceString)

    # Display the message as a QT modal dialog box if the application
    # has started
    if globalData.application is not None:
        message = "<html><body>"
        if savedOK:
            message += "Stack trace and log window content saved in " + excptFileName + ".<br>"
        else:
            message += "Failed to save stack trace and log window content in " + excptFileName + ".<br>"

        lines = stackTraceString.split("\n")
        if len(lines) > 32:
            message += (
                "First 32 lines of the stack trace (the rest is truncated):<pre>" + "\n".join(lines[:32]) + "<pre>"
            )
        else:
            message += "Stack trace:" + "<pre>" + stackTraceString + "</pre>"
        message += "</body></html>"
        QMessageBox.critical(None, "Unhandled exception: " + error, message)
        globalData.application.exit(1)


def main():
    """The main entry point"""
    launcher = CodimensionUILauncher()
    retCode = launcher.main()

    # restore root logging handlers
    if launcher.rootLoggingHandlers:
        logging.root.handlers = launcher.rootLoggingHandlers

    logging.debug("Exiting codimension")
    sys.exit(retCode)


if __name__ == "__main__":
    main()
