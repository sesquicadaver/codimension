# -*- coding: utf-8 -*-
#
# codimension - graphics python two-way code editor and analyzer
# Copyright (C) 2010-2017  Sergey Satskiy sergey.satskiy@gmail.com
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

"""VCS plugin support:
manager to keep track of the VCS plugins and file status"""

import datetime
import logging
import os.path
import time

from plugins.categories.vcsiface import VersionControlSystemInterface
from ui.qt import QObject, QTimer, pyqtSignal
from utils.background_task_registry import get_background_task_registry
from utils.crash_telemetry import note_lifecycle
from utils.globals import GlobalData
from utils.project import CodimensionProject
from utils.settings import Settings

from .indicator import VCSIndicator
from .statuscache import VCSStatus, VCSStatusCache
from .vcspluginthread import IND_VCS_ERROR, VCSPluginThread

# Bounded join when dismissing VCS plugin threads on IDE close (R275).
_VCS_JOIN_TIMEOUT_MS = 5000


class VCSPluginDescriptor(QObject):
    """Holds information about a single active plugin"""

    def __init__(self, manager, pluginID, plugin):
        QObject.__init__(self)

        self.manager = manager
        self.pluginID = pluginID
        self.plugin = plugin
        self.thread = None  # VCSPluginThread
        self.indicators = {}  # ID -> VCSIndicator

        self.__getPluginIndicators()
        self.thread = VCSPluginThread(plugin)
        self.thread.start()

        self.thread.VCSStatus.connect(self.__onStatus)

    def stopThread(self, timeout_ms: int = _VCS_JOIN_TIMEOUT_MS) -> bool:
        """Stop the plugin thread with a bounded wait (R275).

        Returns ``True`` when the thread is not running afterwards. A timeout
        logs a degraded-component warning and returns ``False`` so IDE close
        can continue without an infinite GUI block.
        """
        thread = self.thread
        if thread is None:
            return True
        try:
            thread.clearRequestQueue()
        except Exception:
            logging.debug("VCS clearRequestQueue failed", exc_info=True)
        thread.stop()
        if timeout_ms <= 0:
            return not bool(thread.isRunning())
        finished = bool(thread.wait(max(0, int(timeout_ms))))
        if not finished and thread.isRunning():
            logging.warning(
                "VCS plugin thread '%s' did not finish within %sms; "
                "continuing shutdown in degraded mode (R275)",
                self.getPluginName(),
                timeout_ms,
            )
            note_lifecycle("vcs_shutdown_degraded", detail=self.getPluginName())
            return False
        return True

    def requestStatus(self, path, flag, urgent=False):
        """Requests the item status asynchronously"""
        self.thread.addRequest(path, flag, urgent)

    def clearRequestQueue(self):
        """Clears the thread request queue"""
        self.thread.clearRequestQueue()

    def getPluginName(self):
        """Safe plugin name"""
        try:
            return self.plugin.getName()
        except Exception:
            return "Unknown (could not retrieve)"

    def __getPluginIndicators(self):
        """Retrieves indicators from the plugin"""
        try:
            for indicatorDesc in self.plugin.getObject().getCustomIndicators():
                try:
                    indicator = VCSIndicator(indicatorDesc)
                    if indicator.identifier < 0:
                        logging.error(
                            "Custom VCS plugin '"
                            + self.getPluginName()
                            + "' indicator identifier "
                            + str(indicator.identifier)
                            + " is invalid. It must be >= 0. "
                            "Ignore and continue."
                        )
                    else:
                        self.indicators[indicator.identifier] = indicator
                except Exception as exc:
                    logging.error(
                        "Error getting custom VCS plugin '" + self.getPluginName() + "' indicator: " + str(exc)
                    )
        except Exception as exc:
            logging.error(
                "Error getting custom indicators for a VCS plugin " + self.getPluginName() + ". Exception: " + str(exc)
            )

    def __onStatus(self, path, indicatorId, message):
        """Triggered when the thread reported a status"""
        self.manager.updateStatus(path, self.pluginID, indicatorId, message)

    def canInitiateStatusRequestLoop(self):
        """Returns true if the is no jam in the request queue"""
        return self.thread.canInitiateStatusRequestLoop()


class VCSManager(QObject):
    """Manages the VCS plugins"""

    sigVCSFileStatus = pyqtSignal(str, object)
    sigVCSDirStatus = pyqtSignal(str, object)

    def __init__(self):
        QObject.__init__(self)

        self.dirCache = VCSStatusCache()  # Path -> VCSStatus
        self.fileCache = VCSStatusCache()  # Path -> VCSStatus
        self.activePlugins = {}  # Plugin ID -> VCSPluginDescriptor
        self.systemIndicators = {}  # ID -> VCSIndicator

        self.__firstFreeIndex = 0

        self.__readSettingsIndicators()
        self.__dirRequestLoopTimer = QTimer(self)
        self.__dirRequestLoopTimer.setSingleShot(True)
        self.__dirRequestLoopTimer.timeout.connect(self.__onDirRequestLoopTimer)

        GlobalData().project.sigProjectChanged.connect(self.__onProjectChanged)
        GlobalData().project.sigFSChanged.connect(self.__onFSChanged)
        GlobalData().pluginManager.sigPluginActivated.connect(self.__onPluginActivated)

        # Plugin deactivation must be done via dismissPlugin(...)
        get_background_task_registry().register(
            "vcs",
            cancel=self.requestShutdown,
            wait=self.waitForShutdown,
            is_active=self.hasLiveThreads,
        )

    def hasLiveThreads(self) -> bool:
        """True while any VCS plugin QThread is still running (R275)."""
        for descriptor in self.activePlugins.values():
            thread = getattr(descriptor, "thread", None)
            if thread is not None and bool(thread.isRunning()):
                return True
        return False

    def requestShutdown(self) -> None:
        """Cooperative stop of all VCS plugin threads (R275 / R271)."""
        self.__dirRequestLoopTimer.stop()
        for descriptor in list(self.activePlugins.values()):
            thread = getattr(descriptor, "thread", None)
            if thread is None:
                continue
            try:
                thread.clearRequestQueue()
            except Exception:
                logging.debug("VCS clearRequestQueue failed", exc_info=True)
            thread.stop()

    def waitForShutdown(self, timeout_ms: int = _VCS_JOIN_TIMEOUT_MS) -> bool:
        """Wait until VCS plugin threads stop; shared budget across plugins."""
        remaining_ms = max(0, int(timeout_ms))
        for descriptor in list(self.activePlugins.values()):
            thread = getattr(descriptor, "thread", None)
            if thread is None or not thread.isRunning():
                continue
            if remaining_ms <= 0:
                break
            started = time.monotonic()
            thread.wait(remaining_ms)
            elapsed_ms = int((time.monotonic() - started) * 1000)
            remaining_ms = max(0, remaining_ms - max(elapsed_ms, 0))
        return not self.hasLiveThreads()

    def __getNewPluginIndex(self):
        """Provides a new plugin index"""
        index = self.__firstFreeIndex
        self.__firstFreeIndex += 1
        return index

    def __readSettingsIndicators(self):
        """Reads the system indicators"""
        for indicLine in Settings()["vcsindicators"]:
            indicator = VCSIndicator(indicLine)
            self.systemIndicators[indicator.identifier] = indicator

    def __onPluginActivated(self, plugin):
        """Triggered when a plugin is activated"""
        if plugin.categoryName != "VersionControlSystemInterface":
            return

        newPluginIndex = self.__getNewPluginIndex()
        self.activePlugins[newPluginIndex] = VCSPluginDescriptor(self, newPluginIndex, plugin)
        plugin.getObject().PathChanged.connect(self.__onPathChanged)

        # Need to send requests for the opened TAB files
        mainWindow = GlobalData().mainWindow
        editorsManager = mainWindow.editorsManagerWidget.editorsManager
        editorsManager.sendAllTabsVCSStatusRequest()

        if self.activePluginCount() == 1 and GlobalData().project.isLoaded():
            # This is the first plugin and a project is there
            self.__populateProjectDirectories()
        self.__sendDirectoryRequestsOnActivation(newPluginIndex)
        self.__sendFileRequestsOnActivation(newPluginIndex)

        if self.activePluginCount() == 1:
            self.__startDirRequestTimer()

    def __onPathChanged(self, path):
        """The way plugins signal that a path has been changed"""
        # What is essentially required is to update the status of the path.
        # setLocallyModified(...) will do - it sends urgent request
        self.setLocallyModified(path)

        # Changed paths may change the file contents
        mainWindow = GlobalData().mainWindow
        editorsManager = mainWindow.editorsManagerWidget.editorsManager
        editorsManager.checkOutsidePathChange(path)

    def __populateProjectDirectories(self):
        """Populates the project directories in the dirCache"""
        project = GlobalData().project
        for path in project.filesList:
            if path.endswith(os.path.sep):
                self.dirCache.updateStatus(path, None, None, None, None)

    def __onProjectChanged(self, what):
        """Triggered when a project has changed"""
        if what == CodimensionProject.CompleteProject:
            self.dirCache.clear()
            self.fileCache.clear()
            if len(self.activePlugins) == 0:
                return

            # There are some plugins
            for _, descriptor in self.activePlugins.items():
                descriptor.clearRequestQueue()

            if GlobalData().project.isLoaded():
                self.__populateProjectDirectories()

    def __onFSChanged(self, items):
        """Triggered when files/dirs in the project are changed"""
        for item in items:
            item = str(item)
            if item.startswith("-"):
                item = item[1:]
                if item.endswith(os.path.sep):
                    # Directory removed
                    if item in self.dirCache.cache:
                        del self.dirCache.cache[item]
                else:
                    # File deleted
                    if item in self.fileCache.cache:
                        del self.fileCache.cache[item]
                    for _, descriptor in self.activePlugins.items():
                        descriptor.requestStatus(item, VersionControlSystemInterface.REQUEST_ITEM_ONLY, True)
            else:
                item = item[1:]
                if item.endswith(os.path.sep):
                    # Directory added
                    if item not in self.dirCache.cache:
                        self.dirCache.updateStatus(item, None, None, None, None)
                    for _, descriptor in self.activePlugins.items():
                        descriptor.requestStatus(item, VersionControlSystemInterface.REQUEST_DIRECTORY)
                else:
                    # File added
                    for _, descriptor in self.activePlugins.items():
                        descriptor.requestStatus(item, VersionControlSystemInterface.REQUEST_ITEM_ONLY, True)

    def __sendDirectoryRequestsOnActivation(self, pluginID):
        """Sends the directory requests to the given plugin"""
        descriptor = self.activePlugins[pluginID]
        statuses = [None, VersionControlSystemInterface.NOT_UNDER_VCS]
        for path, status in self.dirCache.cache.items():
            if status.indicatorID in statuses:
                descriptor.requestStatus(path, VersionControlSystemInterface.REQUEST_DIRECTORY)

    def __sendFileRequestsOnActivation(self, pluginID):
        """Sends the file requests to the given plugin"""
        descriptor = self.activePlugins[pluginID]
        statuses = [None, VersionControlSystemInterface.NOT_UNDER_VCS]
        for path, status in self.fileCache.cache.items():
            if status.indicatorID in statuses:
                descriptor.requestStatus(path, VersionControlSystemInterface.REQUEST_ITEM_ONLY)

    def __sendPeriodicDirectoryRequests(self):
        """Sends the directory requests periodically"""
        for path, status in self.dirCache.cache.items():
            if status.pluginID in self.activePlugins:
                # This directory is under certain VCS, send the request
                # only to this VCS
                descriptor = self.activePlugins[status.pluginID]
                descriptor.requestStatus(path, VersionControlSystemInterface.REQUEST_DIRECTORY)
            else:
                # The directory is not under any known VCS. Send the request
                # to all the registered VCS plugins
                for _, descriptor in self.activePlugins.items():
                    descriptor.requestStatus(path, VersionControlSystemInterface.REQUEST_DIRECTORY)

    def dismissAllPlugins(self, timeout_ms: int = _VCS_JOIN_TIMEOUT_MS) -> list[str]:
        """Stop all plugin threads with a bounded wait (R275).

        Returns the names of plugins that did not stop within ``timeout_ms``
        (degraded components). IDE close must not block forever on a hung
        ``getStatus()`` inside a VCS plugin.
        """
        self.__dirRequestLoopTimer.stop()
        degraded: list[str] = []
        remaining_ms = max(0, int(timeout_ms))
        for _identifier, descriptor in list(self.activePlugins.items()):
            try:
                descriptor.plugin.getObject().PathChanged.disconnect(self.__onPathChanged)
            except Exception:
                logging.debug("VCS PathChanged disconnect failed", exc_info=True)
            started = time.monotonic()
            budget = remaining_ms
            if not descriptor.stopThread(timeout_ms=budget):
                degraded.append(descriptor.getPluginName())
            elapsed_ms = int((time.monotonic() - started) * 1000)
            remaining_ms = max(0, remaining_ms - max(elapsed_ms, 0))

        self.dirCache.clear()
        self.fileCache.clear()
        self.activePlugins = {}
        if degraded:
            logging.warning(
                "VCS shutdown degraded for: %s",
                ", ".join(degraded),
            )
            note_lifecycle("vcs_dismiss_degraded", detail=",".join(degraded))
        return degraded

    def dismissPlugin(self, plugin, timeout_ms: int = _VCS_JOIN_TIMEOUT_MS):
        """Stops the plugin thread and cleans the plugin data"""
        pluginID = None
        for identifier, descriptor in self.activePlugins.items():
            if descriptor.getPluginName() == plugin.getName():
                try:
                    descriptor.plugin.getObject().PathChanged.disconnect(self.__onPathChanged)
                except Exception:
                    logging.debug("VCS PathChanged disconnect failed", exc_info=True)
                pluginID = identifier
                descriptor.stopThread(timeout_ms=timeout_ms)
                self.fileCache.dismissPlugin(pluginID, self.sendFileStatusNotification)
                self.dirCache.dismissPlugin(pluginID, self.sendDirStatusNotification)

        if pluginID is not None:
            del self.activePlugins[pluginID]

        if self.activePluginCount() == 0:
            self.__dirRequestLoopTimer.stop()

    def requestStatus(self, path, flag=VersionControlSystemInterface.REQUEST_ITEM_ONLY):
        """Provides the path status asynchronously via sending a signal"""
        delta = datetime.timedelta(0, Settings()["vcsstatusupdateinterval"])
        if path.endswith(os.path.sep):
            status = self.dirCache.getStatus(path)
            if status:
                self.sendDirStatusNotification(path, status)
            else:
                self.sendDirStatusNotification(path, VCSStatus())
        else:
            status = self.fileCache.getStatus(path)
            if status:
                self.sendFileStatusNotification(path, status)
            else:
                self.sendFileStatusNotification(path, VCSStatus())

        if status is None:
            for _, descriptor in self.activePlugins.items():
                descriptor.requestStatus(path, flag, True)
        else:
            if (
                status.indicatorID is None
                or status.lastUpdate is None
                or datetime.datetime.now() - status.lastUpdate > delta
            ):
                # Outdated or never been received
                if status.pluginID in self.activePlugins:
                    # Path is claimed by a plugin
                    descriptor = self.activePlugins[status.pluginID]
                    descriptor.requestStatus(path, flag, True)
                    return
                # Path is not claimed by any plugin - send to all
                for _, descriptor in self.activePlugins.items():
                    descriptor.requestStatus(path, flag, True)

    def setLocallyModified(self, path):
        """Sets the item status as locally modified"""
        for _, descriptor in self.activePlugins.items():
            descriptor.requestStatus(path, VersionControlSystemInterface.REQUEST_ITEM_ONLY, True)

    def sendDirStatusNotification(self, path, status):
        """Sends a signal that a status of the directory is changed"""
        self.sigVCSDirStatus.emit(path, status)

    def sendFileStatusNotification(self, path, status):
        """Sends a signal that a status of the file is changed"""
        self.sigVCSFileStatus.emit(path, status)

    def updateStatus(self, path, pluginID, indicatorID, message):
        """Called when a plugin thread reports a status"""
        if path.endswith(os.path.sep):
            self.dirCache.updateStatus(path, pluginID, indicatorID, message, self.sendDirStatusNotification)
        else:
            self.fileCache.updateStatus(path, pluginID, indicatorID, message, self.sendFileStatusNotification)
        # print("Status of " + path + " is " + str(indicatorID) +
        # " Message: " + str(message) + " Plugin ID: " + str(pluginID))

    def activePluginCount(self):
        """Returns the number of active VCS plugins"""
        return len(self.activePlugins)

    def drawStatus(self, vcsLabel, status):
        """Draw the VCS status"""
        if status.pluginID not in self.activePlugins:
            vcsLabel.setVisible(False)
            return

        descriptor = self.activePlugins[status.pluginID]
        if status.indicatorID not in descriptor.indicators:
            # Check the standard indicator
            if status.indicatorID in self.systemIndicators:
                indicator = self.systemIndicators[status.indicatorID]
                indicator.draw(vcsLabel)
                if status.message:
                    vcsLabel.setToolTip(status.message)
                else:
                    vcsLabel.setToolTip(indicator.defaultTooltip)
            else:
                # Neither plugin, no standard indicator
                try:
                    indicator = self.systemIndicators[IND_VCS_ERROR]
                    indicator.draw(vcsLabel)
                    vcsLabel.setToolTip(
                        "VCS plugin provided undefined indicator (id is " + str(status.indicatorID) + ")"
                    )
                except Exception:
                    # No way to display indicator
                    vcsLabel.setVisible(False)
            return

        indicator = descriptor.indicators[status.indicatorID]
        indicator.draw(vcsLabel)
        if status.message:
            vcsLabel.setToolTip(status.message)
        else:
            vcsLabel.setToolTip(indicator.defaultTooltip)

    def getStatusIndicator(self, status):
        """Provides the VCS status indicator description for the given status.
        It is mostly used for the project browser"""
        if status.pluginID not in self.activePlugins:
            return None

        descriptor = self.activePlugins[status.pluginID]
        if status.indicatorID not in descriptor.indicators:
            # Check the standard indicator
            return self.getSystemIndicator(status.indicatorID)

        return descriptor.indicators[status.indicatorID]

    def getSystemIndicator(self, indicatorID):
        """Provides the IDE defined indicator if so"""
        if indicatorID in self.systemIndicators:
            return self.systemIndicators[indicatorID]
        return None

    def __canInitiateStatusRequestLoop(self):
        """Returns true if the is no jam in the request queue"""
        for _, descriptor in self.activePlugins.items():
            if descriptor.canInitiateStatusRequestLoop():
                return True
        return False

    def __onDirRequestLoopTimer(self):
        """Triggered when the dir request loop timer is fired"""
        self.__dirRequestLoopTimer.stop()
        if self.activePluginCount() == 0:
            return

        if self.__canInitiateStatusRequestLoop():
            self.__sendPeriodicDirectoryRequests()
        self.__startDirRequestTimer()

    def __startDirRequestTimer(self):
        """Starts the periodic request timer"""
        self.__dirRequestLoopTimer.start(Settings()["vcsstatusupdateinterval"] * 1000)
