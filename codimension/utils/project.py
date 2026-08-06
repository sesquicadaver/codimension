# -*- coding: utf-8 -*-
#
# codimension - graphics python two-way code editor and analyzer
# Copyright (C) 2010-2016  Sergey Satskiy <sergey.satskiy@gmail.com>
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


"""codimension project"""

# pylint: disable=W0702
# pylint: disable=W0703

import copy
import json
import logging
import os
import re
import shutil
import uuid
from os.path import basename, dirname, exists, isabs, isfile, join, realpath, relpath, sep

from PyQt5.QtCore import QThread
from PyQt5.QtWidgets import QApplication
from ui.qt import QObject, pyqtSignal

from .atomic_io import atomic_write_text
from .config import DEFAULT_ENCODING
from .debugenv import DebuggerEnvironment
from .filepositions import FilePositions
from .flowgroups import FlowUICollapsedGroups
from .fsenv import FileSystemEnvironment
from .project_scan import ScanCancelled, is_excluded_by_absolute_paths, scan_project_files
from .project_schema import ProjectSchemaError, safe_user_project_dir, validate_project_props
from .runparamscache import RunParametersCache
from .searchenv import SearchEnvironment
from .settings import SETTINGS_DIR, Settings
from .userencodings import FileEncodings
from .venvutils import getProjectVenvDir
from .watcher import Watcher

# Bounded wait when unloading / resetting an in-flight scan (audit B03).
_SCAN_JOIN_TIMEOUT_MS = 5000


class _ProjectScanThread(QThread):
    """Background project tree scan (T052) — keeps GUI responsive."""

    sigDone = pyqtSignal(object, int)  # files set, generation
    sigFailed = pyqtSignal(str, int)

    def __init__(
        self,
        project_dir,
        basename_filters,
        exclude_paths,
        venv_dir,
        generation: int,
        parent=None,
    ):
        QThread.__init__(self, parent)
        self._project_dir = project_dir
        self._basename_filters = basename_filters
        self._exclude_paths = exclude_paths
        self._venv_dir = venv_dir
        self._generation = generation

    def run(self):
        """Scan project tree off the GUI thread with cooperative cancel (B03)."""
        try:
            result = scan_project_files(
                self._project_dir,
                basename_filters=self._basename_filters,
                exclude_absolute_paths=self._exclude_paths,
                venv_dir=self._venv_dir,
                should_cancel=self.isInterruptionRequested,
            )
        except ScanCancelled:
            return
        except Exception as exc:
            if not self.isInterruptionRequested():
                self.sigFailed.emit(str(exc), self._generation)
            return
        if self.isInterruptionRequested():
            return
        self.sigDone.emit(result, self._generation)


# Saved in .cdm3 file
_DEFAULT_PROJECT_PROPS = {
    "scriptname": "",  # Script to run the project
    "mddocfile": "",
    "creationdate": "",
    "author": "",
    "license": "",
    "copyright": "",
    "version": "",
    "email": "",
    "description": "",
    "uuid": "",
    "importdirs": [],
    "excludeFromAnalysis": [],  # Dirs/files to exclude from analysis
    "encoding": "",
    "pythoninterpreter": "",
}  # Optional venv/python path


def new_project_uuid() -> str:
    """Allocate a new project UUID (random; not time-based uuid1)."""
    return str(uuid.uuid4())


def merge_project_defaults(props: dict) -> dict:
    """Fill missing `.cdm3` keys from defaults (mutates and returns ``props``)."""
    for key, value in _DEFAULT_PROJECT_PROPS.items():
        if key not in props:
            props[key] = copy.deepcopy(value)
    return props


def load_validated_project_props(project_file: str) -> dict:
    """Read and schema-validate a `.cdm3` file; never returns ``{}`` on failure."""
    path = realpath(project_file)
    if not exists(path):
        raise Exception("Cannot find project file " + project_file)
    try:
        with open(path, "r", encoding=DEFAULT_ENCODING) as diskfile:
            props = json.load(diskfile)
        return merge_project_defaults(validate_project_props(props))
    except ProjectSchemaError as exc:
        raise Exception("Bad project file " + project_file + ": " + str(exc)) from exc
    except Exception as exc:
        raise Exception("Bad project file " + project_file + ": " + str(exc)) from exc


class CodimensionProject(
    QObject,
    DebuggerEnvironment,
    SearchEnvironment,
    FileSystemEnvironment,
    RunParametersCache,
    FilePositions,
    FileEncodings,
    FlowUICollapsedGroups,
):
    """Provides codimension project singleton facility"""

    # Constants for the sigProjectChanged signal
    CompleteProject = 0  # It is a completely new project
    Properties = 1  # Project properties were updated

    sigProjectChanged = pyqtSignal(int)
    sigFSChanged = pyqtSignal(list)
    sigRestoreProjectExpandedDirs = pyqtSignal()
    sigProjectAboutToUnload = pyqtSignal()
    sigRecentFilesChanged = pyqtSignal()
    sigFilesListReady = pyqtSignal()

    def __init__(self):
        QObject.__init__(self)
        DebuggerEnvironment.__init__(self)
        SearchEnvironment.__init__(self)
        FileSystemEnvironment.__init__(self)
        RunParametersCache.__init__(self)
        FilePositions.__init__(self)
        FileEncodings.__init__(self)
        FlowUICollapsedGroups.__init__(self)

        self.__dirWatcher = None
        self.__scanThread = None
        self.__scanGeneration = 0
        self.__scanOnComplete = None
        self.__scanCoalesce = False
        self.__pendingRestoreExpanded = False

        # Avoid pylint complains
        self.fileName = ""
        self.userProjectDir = ""  # Directory in ~/.codimension3/uuidNN/
        self.filesList = set()

        self.props = copy.deepcopy(_DEFAULT_PROJECT_PROPS)

        # Precompile the exclude filters for the project files list
        self.__excludeFilter = []
        for flt in Settings()["projectFilesFilters"]:
            self.__excludeFilter.append(re.compile(flt))

    def shouldExclude(self, name):
        """Tests if a file must be excluded"""
        if name == ".pylintrc":
            return False
        for excl in self.__excludeFilter:
            if excl.match(name):
                return True
        return False

    def __resetValues(self):
        """Initializes or resets all the project members"""
        # T140: drop session-only interpreter when switching/unloading projects
        from .venvbootstrap import clearSessionPythonInterpreter

        clearSessionPythonInterpreter()

        # Empty file name means that the project has not been loaded or
        # created. This must be an absolute path.
        self.fileName = ""
        self.userProjectDir = ""

        # Generated having the project dir Full paths are stored.
        # The set holds all files and directories.
        # The dirs end with os.path.sep
        self.filesList = set()

        self.props = copy.deepcopy(_DEFAULT_PROJECT_PROPS)

        RunParametersCache.reset(self)
        DebuggerEnvironment.reset(self)
        SearchEnvironment.reset(self)
        FileSystemEnvironment.reset(self)
        FilePositions.reset(self)
        FileEncodings.reset(self)
        FlowUICollapsedGroups.reset(self)

        # Reset the dir watchers if so
        self.__cancelScan()
        self.__pendingRestoreExpanded = False
        if self.__dirWatcher is not None:
            del self.__dirWatcher
            self.__dirWatcher = None

    def createNew(self, fileName, props):
        """Creates a new project"""
        # Try to create the user project directory (canonical UUID under SETTINGS_DIR)
        try:
            validated = merge_project_defaults(validate_project_props(copy.deepcopy(props)))
        except ProjectSchemaError as exc:
            logging.error("Cannot create project with invalid properties: %s", exc)
            raise
        projectUuid = new_project_uuid()
        try:
            userProjectDir = safe_user_project_dir(SETTINGS_DIR, projectUuid)
        except ProjectSchemaError as exc:
            logging.error("Cannot create user project directory: %s", exc)
            raise
        if not exists(userProjectDir):
            try:
                os.makedirs(userProjectDir)
            except Exception:
                logging.error(
                    "Cannot create user project directory: %s. "
                    "Please check the available disk space, "
                    "permissions and re-create the project.",
                    userProjectDir,
                )
                raise
        else:
            logging.warning("The user project directory exists! The content will be overwritten.")
            self.__removeProjectFiles(userProjectDir)

        # Basic pre-requisites are met. We can reset the current project.
        self.__resetValues()

        self.fileName = fileName
        validated["uuid"] = projectUuid
        self.props = validated
        self.userProjectDir = userProjectDir

        self.__createProjectFile()  # ~/.codimension3/uuidNN/project

        RunParametersCache.setup(self, self.userProjectDir)
        DebuggerEnvironment.setup(self, self.userProjectDir)
        SearchEnvironment.setup(self, self.userProjectDir)
        FileSystemEnvironment.setup(self, self.userProjectDir)
        FilePositions.setup(self, self.userProjectDir)
        FileEncodings.setup(self, self.userProjectDir)
        FlowUICollapsedGroups.setup(self, self.userProjectDir)

        self.saveProject()
        # CompleteProject only after filesList is ready (T052 contract)
        self.__generateFilesList(on_complete=self.__finishProjectOpen)

    @staticmethod
    def __removeProjectFiles(userProjectDir):
        """Removes user project files"""
        for root, dirs, files in os.walk(userProjectDir):
            for f in files:
                try:
                    os.unlink(join(root, f))
                except Exception:
                    pass
            for d in dirs:
                try:
                    shutil.rmtree(join(root, d))
                except Exception:
                    pass

    def __createProjectFile(self):
        """Helper function to create the user project file"""
        try:
            atomic_write_text(self.userProjectDir + "project", self.fileName, encoding=DEFAULT_ENCODING)
        except Exception as exc:
            logging.error("Could not create the %s project file: %s", self.userProjectDir, str(exc))

    def saveProject(self):
        """Writes all the settings into the file"""
        if not self.isLoaded():
            return

        # It could be another user project file without write permissions
        skipProjectFile = False
        if exists(self.fileName):
            if not os.access(self.fileName, os.W_OK):
                skipProjectFile = True
        else:
            if not os.access(dirname(self.fileName), os.W_OK):
                skipProjectFile = True

        if not skipProjectFile:
            payload = json.dumps(self.props, indent=4) + "\n"
            atomic_write_text(self.fileName, payload, encoding=DEFAULT_ENCODING)
        else:
            logging.warning("Skipping updates in %s due to writing permissions", self.fileName)

    def loadProject(self, projectFile):
        """Loads a project from the given file"""
        path = realpath(projectFile)
        if not exists(path):
            raise Exception("Cannot open project file " + projectFile)
        if not path.endswith(".cdm3"):
            raise Exception("Unexpected project file extension. Expected: .cdm3")

        try:
            props = load_validated_project_props(path)
        except Exception as exc:
            # Preserve message shape for callers
            raise Exception(str(exc)) from exc

        self.__resetValues()
        self.fileName = path
        self.props = props

        uuid_migrated = False
        if self.props["uuid"] == "":
            logging.warning("Project file does not have UUID. Re-generate it...")
            self.props["uuid"] = new_project_uuid()
            uuid_migrated = True
        try:
            self.userProjectDir = safe_user_project_dir(SETTINGS_DIR, self.props["uuid"])
        except ProjectSchemaError as exc:
            raise Exception("Bad project file " + projectFile + ": " + str(exc)) from exc
        if not exists(self.userProjectDir):
            os.makedirs(self.userProjectDir)

        # Read the other config files
        DebuggerEnvironment.setup(self, self.userProjectDir)
        SearchEnvironment.setup(self, self.userProjectDir)
        FileSystemEnvironment.setup(self, self.userProjectDir)
        RunParametersCache.setup(self, self.userProjectDir)
        FilePositions.setup(self, self.userProjectDir)
        FileEncodings.setup(self, self.userProjectDir)
        FlowUICollapsedGroups.setup(self, self.userProjectDir)

        # The project might have been moved...
        self.__createProjectFile()  # ~/.codimension3/uuidNN/project

        # Persist migrated UUID immediately so the next open reuses the same state dir (C05).
        if uuid_migrated:
            self.saveProject()

        # Update the recent list
        Settings().addRecentProject(self.fileName)

        # CompleteProject only after filesList is ready (T052 contract)
        self.__pendingRestoreExpanded = True
        self.__generateFilesList(on_complete=self.__finishProjectOpen)

    def __finishProjectOpen(self):
        """Watcher + CompleteProject after filesList is consistent."""
        if self.__dirWatcher is not None:
            try:
                self.__dirWatcher.deleteLater()
            except Exception:
                pass
            self.__dirWatcher = None
        self.__dirWatcher = self.__createWatcher()
        self.__dirWatcher.sigFSChanged.connect(self.onFSChanged)
        self.sigProjectChanged.emit(self.CompleteProject)
        if self.__pendingRestoreExpanded:
            self.__pendingRestoreExpanded = False
            self.sigRestoreProjectExpandedDirs.emit()

    def __finishAnalysisRescan(self):
        """Recreate watcher and emit CompleteProject after rescan."""
        if self.__dirWatcher is not None:
            try:
                self.__dirWatcher.deleteLater()
            except Exception:
                pass
            self.__dirWatcher = None
        self.__dirWatcher = self.__createWatcher()
        self.__dirWatcher.sigFSChanged.connect(self.onFSChanged)
        self.sigProjectChanged.emit(self.CompleteProject)

    def __getWatcherExcludeFilters(self):
        """Basename regex filters only (Settings). Path excludes are absolute (T050)."""
        return list(Settings()["projectFilesFilters"])

    def __getWatcherExcludeAbsolutePaths(self):
        """Absolute paths excluded from watch/scan (venv + excludeFromAnalysis)."""
        paths = list(self.getExcludeFromAnalysisAsAbsolutePaths())
        venv_dir = getProjectVenvDir(self)
        if venv_dir:
            paths.append(realpath(venv_dir))
        return paths

    def __createWatcher(self):
        """Create filesystem watcher with path-aware excludes."""
        return Watcher(
            self.__getWatcherExcludeFilters(),
            self.getProjectDir(),
            excludeAbsolutePaths=self.__getWatcherExcludeAbsolutePaths(),
        )

    def getImportDirsAsAbsolutePaths(self):
        """Provides a list of import dirs as absolute paths"""
        result = []
        for path in self.props["importdirs"]:
            if isabs(path):
                result.append(path)
            else:
                result.append(self.getProjectDir() + path)
        return result

    def getExcludeFromAnalysisAsAbsolutePaths(self):
        """Provides a list of absolute paths to exclude from analysis."""
        result = []
        proj_dir = self.getProjectDir()
        for path in self.props.get("excludeFromAnalysis", []):
            path = path.strip()
            if not path:
                continue
            if isabs(path):
                result.append(realpath(path))
            else:
                result.append(realpath(proj_dir + path))
        return result

    def __isExcludedFromAnalysis(self, candidate_path):
        """True if candidate_path should be excluded from analysis."""
        return is_excluded_by_absolute_paths(candidate_path, self.getExcludeFromAnalysisAsAbsolutePaths())

    def onFSChanged(self, items):
        """Triggered when the watcher detects changes"""
        for item in items:
            try:
                if item.startswith("+"):
                    self.filesList.add(item[1:])
                else:
                    self.filesList.remove(item[1:])
            except Exception:
                pass
        self.sigFSChanged.emit(items)

    def unloadProject(self, emitSignal=True):
        """Unloads the current project if required"""
        self.sigProjectAboutToUnload.emit()
        self.__resetValues()
        if emitSignal:
            # No need to send a signal e.g. if IDE is closing
            self.sigProjectChanged.emit(self.CompleteProject)

    def setImportDirs(self, paths):
        """Sets a new set of the project import dirs"""
        if self.props["importdirs"] != paths:
            self.props["importdirs"] = paths
            self.saveProject()
            self.sigProjectChanged.emit(self.Properties)

    def __cancelScan(self, *, join_ms: int = _SCAN_JOIN_TIMEOUT_MS):
        """Interrupt any in-flight background scan (audit B03).

        Drops the post-scan callback, invalidates the generation counter, requests
        cooperative interruption, and optionally waits a bounded time. The
        thread is cleaned via ``finished`` → ``deleteLater``.
        """
        self.__scanGeneration += 1
        self.__scanOnComplete = None
        self.__scanCoalesce = False
        thread = self.__scanThread
        if thread is None:
            return
        thread.requestInterruption()
        if join_ms > 0:
            if not thread.wait(join_ms):
                logging.warning("Project scan thread did not finish within %sms", join_ms)
        if thread is self.__scanThread:
            self.__scanThread = None

    def __invokeScanComplete(self):
        """Run and clear the pending post-scan callback."""
        callback = self.__scanOnComplete
        self.__scanOnComplete = None
        if callback is not None:
            callback()

    def __scanSync(self):
        """Synchronous project tree scan (tests / no QApplication)."""
        path = self.getProjectDir()
        self.filesList = scan_project_files(
            path,
            basename_filters=self.__excludeFilter,
            exclude_absolute_paths=self.getExcludeFromAnalysisAsAbsolutePaths(),
            venv_dir=getProjectVenvDir(self),
            should_exclude=self.shouldExclude,
        )
        self.sigFilesListReady.emit()

    def __startScanThread(self, generation: int) -> None:
        """Start a background scan for ``generation`` (caller owns coalesce flags)."""
        if not self.filesList:
            self.filesList = {self.getProjectDir()}
        thread = _ProjectScanThread(
            self.getProjectDir(),
            list(self.__excludeFilter),
            self.getExcludeFromAnalysisAsAbsolutePaths(),
            getProjectVenvDir(self),
            generation,
            parent=self,
        )
        self.__scanThread = thread
        thread.sigDone.connect(self.__onScanDone)
        thread.sigFailed.connect(self.__onScanFailed)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self.__onScanThreadFinished)
        thread.start()

    def __onScanThreadFinished(self) -> None:
        """Clear thread ref and start a coalesced rescan if one was queued (B03)."""
        thread = self.sender()
        if thread is self.__scanThread:
            self.__scanThread = None
        if not self.__scanCoalesce:
            return
        if not self.isLoaded() or QApplication.instance() is None:
            self.__scanCoalesce = False
            return
        self.__scanCoalesce = False
        self.__startScanThread(self.__scanGeneration)

    def __generateFilesList(self, *, sync=None, on_complete=None):
        """Generate filesList; async when QApplication exists (T052 / B03).

        Concurrent requests coalesce: the in-flight scan is interrupted and a
        single replacement scan runs after it finishes. ``on_complete`` runs
        only after ``filesList`` is populated so callers can emit
        ``CompleteProject`` with a consistent project tree.
        """
        if sync is None:
            sync = QApplication.instance() is None
        if sync:
            self.__cancelScan()
            self.__scanOnComplete = on_complete
            self.__scanSync()
            self.__invokeScanComplete()
            return

        # Latest callback wins when scans are coalesced.
        self.__scanOnComplete = on_complete
        if self.__scanThread is not None and self.__scanThread.isRunning():
            self.__scanGeneration += 1
            self.__scanCoalesce = True
            self.__scanThread.requestInterruption()
            return

        self.__scanGeneration += 1
        self.__scanCoalesce = False
        self.__startScanThread(self.__scanGeneration)

    def __onScanDone(self, result, generation):
        """Apply background scan results if still current."""
        if generation != self.__scanGeneration:
            return
        self.filesList = result if isinstance(result, set) else set(result)
        self.__scanThread = None
        self.sigFilesListReady.emit()
        self.__invokeScanComplete()

    def __onScanFailed(self, message, generation):
        """Log scan failure without blocking the GUI on a sync rescan (B03)."""
        if generation != self.__scanGeneration:
            return
        logging.error("Project scan failed: %s", message)
        self.__scanThread = None
        # Keep the last known filesList; never fall back to sync I/O on the GUI thread.
        self.__invokeScanComplete()

    def isProjectDir(self, path):
        """Returns True if the path belongs to the project"""
        if not self.isLoaded():
            return False
        path = realpath(path)  # it could be a symlink
        if not path.endswith(sep):
            path += sep
        return path.startswith(self.getProjectDir())

    def isProjectFile(self, path):
        """Returns True if the path belongs to the project"""
        if not self.isLoaded():
            return False
        return self.isProjectDir(dirname(path))

    def isTopLevelDir(self, path):
        """Checks if the path is a top level dir"""
        if not path.endswith(sep):
            path += sep
        return path in self.topLevelDirs

    def updateProperties(self, props):
        """Updates the project properties via the same schema pipeline as load (B09)."""
        try:
            validated = merge_project_defaults(validate_project_props(copy.deepcopy(props)))
        except ProjectSchemaError as exc:
            logging.error("Rejecting invalid project properties update: %s", exc)
            raise
        # Keep existing UUID when the dialog omits / blanks it.
        if not validated.get("uuid") and self.props.get("uuid"):
            validated["uuid"] = self.props["uuid"]
        if self.props != validated:
            analysis_props = ("excludeFromAnalysis", "importdirs", "pythoninterpreter")
            need_rescan = any(self.props.get(p) != validated.get(p) for p in analysis_props)
            self.props = validated
            self.saveProject()
            if need_rescan:
                # CompleteProject after filesList is ready
                self.__generateFilesList(on_complete=self.__finishAnalysisRescan)
            else:
                self.sigProjectChanged.emit(self.Properties)

    def refreshAnalysisEnvironment(self):
        """Rescan after interpreter / site-packages change (T141).

        Used when props did not change (session overlay, pip sync into the same
        interpreter) but import resolution must pick up a new environment.
        """
        if not self.isLoaded():
            return
        self.__generateFilesList(on_complete=self.__finishAnalysisRescan)

    def onProjectFileUpdated(self):
        """Reload `.cdm3` from disk; keep last-known-good props on validation failure."""
        try:
            props = load_validated_project_props(self.fileName)
        except Exception as exc:
            logging.error(
                "Ignoring invalid project file edit (%s); keeping last-known-good props: %s",
                self.fileName,
                exc,
            )
            return
        self.props = props
        # no need to save, but signal just in case
        self.sigProjectChanged.emit(self.Properties)

    def isLoaded(self):
        """Returns True if a project is loaded"""
        return self.fileName != ""

    def getProjectDir(self):
        """Provides an absolute path to the project dir"""
        if not self.isLoaded():
            return None
        return dirname(realpath(self.fileName)) + sep

    def getProjectName(self):
        """Provides the project name or None"""
        if not self.isLoaded():
            return None

        fBaseName = basename(self.fileName)
        if "." in fBaseName:
            return fBaseName.split(".")[0].strip()
        return fBaseName

    def getProjectScript(self):
        """Provides the project script file name"""
        if not self.isLoaded():
            return None
        if self.props["scriptname"] == "":
            return None
        if isabs(self.props["scriptname"]):
            return self.props["scriptname"]
        return realpath(self.getProjectDir() + self.props["scriptname"])

    def addRecentFile(self, path):
        """Adds a recent file. True if a new file was inserted."""
        ret = FileSystemEnvironment.addRecentFile(self, path)
        if ret:
            self.sigRecentFilesChanged.emit()
        return ret

    def getRelativePath(self, path):
        """Provides a relative path if so"""
        if self.isProjectFile(path):
            return relpath(path, dirname(self.fileName))
        return path

    def getAbsolutePath(self, path):
        """Provides an absolute path if so"""
        if isabs(path):
            return path
        if self.isLoaded():
            return join(dirname(self.fileName), path)
        return path

    def getStartupMarkdownFile(self):
        """Provides the startup documentation markdown file if so"""
        if not self.isLoaded():
            return None
        # Could be in project properties
        if not self.props["mddocfile"]:
            return None
        if isabs(self.props["mddocfile"]):
            return self.props["mddocfile"]
        return realpath(self.getProjectDir() + self.props["mddocfile"])

    def findStartupMarkdownFile(self):
        """Finds the startup MD doc file"""
        if not self.isLoaded():
            return None, None
        fName = self.getStartupMarkdownFile()
        if fName:
            if not isabs(fName):
                fName = self.getAbsolutePath(fName)
            if not exists(fName):
                return None, "Configured markdown doc file " + self.getStartupMarkdownFile() + " is not found"
            return fName, None

        # check the file system
        projectDir = self.getProjectDir()
        for item in os.listdir(projectDir):
            if isfile(projectDir + item):
                lowerName = item.lower()
                if lowerName.endswith(".md") and lowerName.startswith("readme"):
                    return projectDir + item, None
        return None, None

    def suggestStartupMarkdownFile(self):
        """Suggests the default project doc file name"""
        if not self.isLoaded():
            raise Exception("Invalid logic. A markdown project doc file name is requested without a loaded project")
        return self.getProjectDir() + "README.md"


def getProjectProperties(projectFile):
    """Provides validated project properties or throws an exception (B09)."""
    return load_validated_project_props(projectFile)


def getProjectFileTooltip(fileName):
    """Provides a project file tooltip"""
    try:
        props = getProjectProperties(fileName)
    except Exception:
        props = {}
    return "\n".join(
        [
            "Version: " + props.get("version", "n/a"),
            "Description: " + props.get("description", "n/a"),
            "Author: " + props.get("author", "n/a"),
            "e-mail: " + props.get("email", "n/a"),
            "Copyright: " + props.get("copyright", "n/a"),
            "License: " + props.get("license", "n/a"),
            "Creation date: " + props.get("creationdate", "n/a"),
            "Default encoding: " + props.get("encoding", "n/a"),
            "UUID: " + props.get("uuid", "n/a"),
        ]
    )
