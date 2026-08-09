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

"""Provides the storage for the file system environment"""

import os.path
from copy import deepcopy
from typing import Any

from .fileutils import loadJSON, saveJSON

# toplevel dirs: those which are added to the file system browser
# filebrowserexpandeddirs: dirs in the project browser which were expanded when
# the user closed the project
_DEFAULT_FS_PROPS: dict[str, list[Any]] = {
    "tabs": [],  # [bool: active,
    #  string: path, ...]
    "recent": [],  # [path, ...]
    "fsbrowserexpandeddirs": [],  # [path, ...]
    "topleveldirs": [],
}  # [path, ...]


def is_transient_recent_path(path: str) -> bool:
    """True for pytest/temp host paths that must not pollute Recent files."""
    if not path:
        return True
    normalized = os.path.normpath(path).replace("\\", "/")
    parts = [part for part in normalized.split("/") if part]
    for part in parts:
        if part.startswith("pytest-of-"):
            return True
        if part.startswith("pytest-"):
            suffix = part[len("pytest-") :]
            if suffix.isdigit():
                return True
    # Codimension T130 full-IDE smoke leftover directory name.
    if "t130-script" in parts:
        return True
    return False


def prune_recent_files(files: list[str] | None) -> list[str]:
    """Drop missing, transient, and duplicate recent paths (order preserved)."""
    seen: set[str] = set()
    out: list[str] = []
    for path in files or []:
        if not path or path in seen:
            continue
        if is_transient_recent_path(path):
            continue
        if not os.path.exists(path):
            continue
        seen.add(path)
        out.append(path)
    return out


class FileSystemEnvironment:
    """Loads/stores/saves the fs related environment"""

    def __init__(self):
        self.__props = deepcopy(_DEFAULT_FS_PROPS)
        self.__fseFileName = None

        # Default. Could be updated later.
        self.__limit = 32

    def reset(self):
        """Resets the binding to the file system"""
        self.__props = deepcopy(_DEFAULT_FS_PROPS)
        self.__fseFileName = None

    def setup(self, dirName):
        """Binds the parameters to a disk file"""
        # Just in case - flush the previous data if they were bound
        FileSystemEnvironment.save(self)

        dirName = os.path.realpath(dirName)
        if not dirName.endswith(os.path.sep):
            dirName += os.path.sep
        if not os.path.isdir(dirName):
            raise Exception(
                "Directory name is expected for the file system environment. The given " + dirName + " is not."
            )

        self.__fseFileName = dirName + "fsenv.json"
        if os.path.exists(self.__fseFileName):
            FileSystemEnvironment.load(self)

    def load(self):
        """Loads the saved file system environment"""
        if self.__fseFileName:
            default = deepcopy(_DEFAULT_FS_PROPS)
            self.__props = loadJSON(self.__fseFileName, "file system environment", default)
            self.__prune_recent_on_disk()

    def save(self):
        """Saves the file system environment into a file"""
        if self.__fseFileName:
            saveJSON(self.__fseFileName, self.__props, "file system environment")

    def setLimit(self, newLimit):
        """Sets the new limit to the number of entries"""
        self.__limit = newLimit

    def __prune_recent_on_disk(self) -> None:
        """Persist a cleaned recent list after load when stale entries exist."""
        recent = self.__props.get("recent") or []
        pruned = prune_recent_files(recent)
        if pruned != recent:
            self.__props["recent"] = pruned
            FileSystemEnvironment.save(self)

    @property
    def tabStatus(self):
        """Provides the opened tabs status"""
        return self.__props["tabs"]

    @tabStatus.setter
    def tabStatus(self, newStatus):
        self.__props["tabs"] = newStatus
        FileSystemEnvironment.save(self)

    @property
    def recentFiles(self):
        """Provides the recently used files list"""
        return self.__props["recent"]

    @recentFiles.setter
    def recentFiles(self, files):
        self.__props["recent"] = prune_recent_files(files)
        FileSystemEnvironment.save(self)

    def addRecentFile(self, path):
        """Adds a single recent file. True if a new file was inserted."""
        if not path or is_transient_recent_path(path) or not os.path.exists(path):
            return False
        if path in self.__props["recent"]:
            self.__props["recent"].remove(path)
            self.__props["recent"].insert(0, path)
            FileSystemEnvironment.save(self)
            return False
        self.__props["recent"].insert(0, path)
        if len(self.__props["recent"]) > self.__limit:
            self.__props["recent"] = self.__props["recent"][0 : self.__limit]
        FileSystemEnvironment.save(self)
        return True

    def removeRecentFile(self, path):
        """Removes a single recent file"""
        if path in self.__props["recent"]:
            self.__props["recent"].remove(path)
            FileSystemEnvironment.save(self)

    @property
    def fsBrowserExpandedDirs(self):
        """Provides the file system browser expanded dirs"""
        return self.__props["fsbrowserexpandeddirs"]

    @fsBrowserExpandedDirs.setter
    def fsBrowserExpandedDirs(self, newDirs):
        self.__props["fsbrowserexpandeddirs"] = newDirs
        FileSystemEnvironment.save(self)

    @property
    def topLevelDirs(self):
        """Provides a list of dirs in the FS browser"""
        return self.__props["topleveldirs"]

    @topLevelDirs.setter
    def topLevelDirs(self, newDirs):
        self.__props["topleveldirs"] = newDirs
        FileSystemEnvironment.save(self)

    def addTopLevelDir(self, path):
        """Adds a top level dir"""
        if not path.endswith(os.path.sep):
            path += os.path.sep
        if path not in self.__props["topleveldirs"]:
            self.__props["topleveldirs"].append(path)
            FileSystemEnvironment.save(self)

    def removeTopLevelDir(self, path):
        """Removes a top level dir"""
        if not path.endswith(os.path.sep):
            path += os.path.sep
        if path in self.__props["topleveldirs"]:
            self.__props["topleveldirs"].remove(path)
            FileSystemEnvironment.save(self)
