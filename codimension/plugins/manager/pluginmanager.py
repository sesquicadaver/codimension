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

"""Codimension plugin manager"""

import logging
import os.path
import sys

from packaging.version import Version
from plugins.capabilities import negotiate_plugin_capabilities
from ui.qt import QObject, pyqtSignal
from utils.settings import SETTINGS_DIR, Settings
from yapsy.PluginManager import PluginManager

# List of the supported plugin categories, i.e. base class names
CATEGORIES = ["VersionControlSystemInterface", "WizardInterface"]


def isVirtualEnvironment():
    """True if the virtual environment is active"""
    return hasattr(sys, "real_prefix") or sys.base_prefix != sys.prefix


def bundledPluginSearchPaths() -> list[str]:
    """Return directories that may contain bundled ``*.cdmp`` plugins (D07/B08).

    Prefer the installed ``cdmplugins`` package location — ``sys.argv[0]``-relative
    paths break under pytest, wheel entry points, and many launcher layouts.
    """
    paths: list[str] = []
    try:
        import cdmplugins

        bundled = os.path.dirname(os.path.abspath(cdmplugins.__file__))
        if os.path.isdir(bundled):
            paths.append(bundled)
    except ImportError:
        pass

    if isVirtualEnvironment():
        argv_candidate = os.path.normpath(os.path.dirname(sys.argv[0]) + "/../cdmplugins")
        if os.path.isdir(argv_candidate) and argv_candidate not in paths:
            paths.append(argv_candidate)

    for path in sys.path:
        if not path.endswith(("/site-packages", "\\site-packages")):
            continue
        candidate = os.path.join(path, "cdmplugins")
        if os.path.isdir(candidate) and candidate not in paths:
            paths.append(candidate)
    return paths


class CDMPluginManager(PluginManager, QObject):
    """Implements the codimension plugin manager"""

    sigPluginActivated = pyqtSignal(object)
    sigPluginDeactivated = pyqtSignal(object)

    NO_CONFLICT = 0
    # Same name plugin in system and user locations
    SYSTEM_USER_CONFLICT = 1
    # Plugin required incompatible version
    INCOMPATIBLE_IDE_VERSION_CONFLICT = 2
    # Newer version of the same name plugin
    VERSION_CONFLICT = 3
    # Does not derive from any of the supported interface
    BAD_BASE_CLASS = 4
    # The plugin raised exception during activation
    BAD_ACTIVATION = 5
    # Exception on basic methods
    BAD_INTERFACE = 6
    USER_DISABLED = 7
    # Plugin API / capability negotiation failed (R150)
    INCOMPATIBLE_CAPABILITIES = 8

    def __init__(self):
        QObject.__init__(self)

        searchPaths = [SETTINGS_DIR + "plugins", "/usr/share/codimension3-plugins"]
        for candidate in bundledPluginSearchPaths():
            if candidate not in searchPaths:
                searchPaths.append(candidate)

        PluginManager.__init__(self, None, searchPaths, "cdmp")

        self.inactivePlugins = {}  # Categorized inactive plugins
        self.activePlugins = {}  # Categorized active plugins
        self.unknownPlugins = []  # Unknown plugins
        # R191/A210: candidates skipped before import (path → yapsy candidate tuple)
        self._pendingImportByPath: dict[str, tuple] = {}
        self._policySkippedCandidates: list[tuple] = []

    def load(self):
        """Loads the found plugins"""
        from core.safe_mode import is_safe_mode_enabled, safe_mode_reason

        if is_safe_mode_enabled():
            import logging

            logging.info(
                "PluginManager.load skipped (%s)",
                safe_mode_reason() or "safe mode",
            )
            return

        # yapsy still needs a full ``imp`` surface on Python 3.12+ (package plugins).
        try:
            from imp_compat import ensure_imp_compat
        except ImportError:  # pragma: no cover - package layout variant
            from codimension.imp_compat import ensure_imp_compat  # type: ignore[no-redef]

        ensure_imp_compat()

        # Now, let's check the plugins. They must be of known category.
        # R191: disabled paths are filtered inside collectPlugins before import.
        collectedPlugins = self.__collect()
        self.__registerPolicySkippedPlugins()
        self.__applyDisabledPlugins(collectedPlugins)

        self.__checkIDECompatibility(collectedPlugins)
        self.__checkCapabilities(collectedPlugins)
        self.__sysVsUserConflicts(collectedPlugins)
        self.__categoryConflicts(collectedPlugins)
        self.__activatePlugins(collectedPlugins)

        self.saveDisabledPlugins()

    def collectPlugins(self):
        """Locate plugins, skip disabled paths, then import the rest (R191/A210).

        Yapsy's default ``collectPlugins`` imports every candidate. Policy-disabled
        plugins must never execute plugin code until the user enables them.
        """
        self.locatePlugins()
        self._policySkippedCandidates = []
        self._pendingImportByPath = {}
        disabled_paths = self.__disabledPluginPathSet()
        if not disabled_paths:
            self.loadPlugins()
            return

        kept: list[tuple] = []
        for candidate in list(getattr(self, "_candidates", []) or []):
            _info_file, _filepath, plugin_info = candidate
            norm = normalize_plugin_path(plugin_info.path)
            if norm in disabled_paths:
                logging.info(
                    "Skipping import of disabled plugin at %s (manifest-only; R191/A210)",
                    norm,
                )
                self._policySkippedCandidates.append(candidate)
                self._pendingImportByPath[norm] = candidate
                continue
            kept.append(candidate)
        self._candidates = kept
        self.loadPlugins()

    def materializePlugin(self, cdm_plugin: "CDMPluginInfo") -> None:
        """Import a previously policy-skipped plugin module (enable path)."""
        if cdm_plugin.getObject() is not None:
            return
        norm = normalize_plugin_path(cdm_plugin.getPath())
        candidate = self._pendingImportByPath.pop(norm, None)
        if candidate is None:
            raise RuntimeError(f"No deferred import available for plugin at {norm}")
        self._candidates = [candidate]
        self.loadPlugins()
        if cdm_plugin.getObject() is None:
            raise RuntimeError(f"Failed to import deferred plugin at {norm}")
        if not cdm_plugin.categoryName:
            bases = getBaseClassNames(cdm_plugin.getObject())
            for category in CATEGORIES:
                if category in bases:
                    cdm_plugin.categoryName = category
                    break

    def __disabledPluginPathSet(self) -> set[str]:
        """Return normalized paths listed in Settings ``disabledPlugins``."""
        paths: set[str] = set()
        for disabledPlugin in Settings()["disabledPlugins"]:
            try:
                _conflict_type, path, _message = CDMPluginInfo.parseDisabledLine(disabledPlugin)
            except Exception as exc:
                logging.warning(str(exc))
                continue
            paths.add(normalize_plugin_path(path))
        return paths

    def __disabledPluginRecords(self) -> dict[str, tuple[int, str]]:
        """Map normalized path → (conflictType, conflictMessage)."""
        records: dict[str, tuple[int, str]] = {}
        for disabledPlugin in Settings()["disabledPlugins"]:
            try:
                conflict_type, path, message = CDMPluginInfo.parseDisabledLine(disabledPlugin)
            except Exception as exc:
                logging.warning(str(exc))
                continue
            records[normalize_plugin_path(path)] = (conflict_type, message)
        return records

    def __registerPolicySkippedPlugins(self) -> None:
        """Register manifest-only stubs for plugins skipped before import (R191)."""
        records = self.__disabledPluginRecords()
        for candidate in self._policySkippedCandidates:
            _info_file, filepath, plugin_info = candidate
            norm = normalize_plugin_path(plugin_info.path)
            conflict_type, message = records.get(
                norm,
                (CDMPluginManager.USER_DISABLED, "Disabled by user policy"),
            )
            stub = CDMPluginInfo(plugin_info)
            stub.isEnabled = False
            stub.conflictType = conflict_type
            stub.conflictMessage = message or "Disabled by user policy"
            category = guess_plugin_category_from_source(filepath)
            if category:
                stub.categoryName = category
                if category in self.inactivePlugins:
                    self.inactivePlugins[category].append(stub)
                else:
                    self.inactivePlugins[category] = [stub]
            else:
                self.unknownPlugins.append(stub)

    def __collect(self):
        """Checks that the plugins belong to what is known"""
        self.collectPlugins()

        collectedPlugins = {}
        for plugin in self.getAllPlugins():
            recognised = False
            baseClasses = getBaseClassNames(plugin.plugin_object)
            for category in CATEGORIES:
                if category in baseClasses:
                    # OK, this plugin base has been recognised
                    recognised = True
                    newPlugin = CDMPluginInfo(plugin)
                    newPlugin.categoryName = category
                    if category in collectedPlugins:
                        collectedPlugins[category].append(newPlugin)
                    else:
                        collectedPlugins[category] = [newPlugin]
                    break

            if not recognised:
                logging.warning(
                    "Plugin of an unknown category is found at: " + plugin.path + ". The plugin is disabled."
                )
                newPlugin = CDMPluginInfo(plugin)
                newPlugin.conflictType = CDMPluginManager.BAD_BASE_CLASS
                newPlugin.conflictMessage = "The plugin does not derive any known plugin category interface"
                self.unknownPlugins.append(newPlugin)

        return collectedPlugins

    def __activatePlugins(self, collectedPlugins):
        """Activating the plugins"""
        from utils.globals import GlobalData

        for category in collectedPlugins:
            for plugin in collectedPlugins[category]:
                try:
                    plugin.getObject().activate(Settings(), GlobalData())
                    if category in self.activePlugins:
                        self.activePlugins[category].append(plugin)
                    else:
                        self.activePlugins[category] = [plugin]
                    self.sendPluginActivated(plugin)
                except Exception as excpt:
                    logging.error(
                        "Error activating plugin at "
                        + plugin.getPath()
                        + ". The plugin disabled. Error message: \n"
                        + str(excpt)
                    )
                    plugin.conflictType = CDMPluginManager.BAD_ACTIVATION
                    plugin.conflictMessage = "Error activating the plugin"
                    if category in self.inactivePlugins:
                        self.inactivePlugins[category].append(plugin)
                    else:
                        self.inactivePlugins[category] = [plugin]

    def __checkIDECompatibility(self, collectedPlugins):
        """Checks that the plugins can be used with the current IDE"""
        from utils.globals import GlobalData

        toBeRemoved = []
        for category in collectedPlugins:
            for plugin in collectedPlugins[category]:
                try:
                    ideVer = GlobalData().version
                    if not plugin.getObject().isIDEVersionCompatible(ideVer):
                        # The plugin is incompatible. Disable it
                        logging.warning(
                            "The IDE version does not meet the " + plugin.getName() + " plugin "
                            "requirements. The plugin is disabled."
                            " (plugin path: " + plugin.getPath() + ")"
                        )
                        plugin.conflictType = CDMPluginManager.INCOMPATIBLE_IDE_VERSION_CONFLICT
                        plugin.conflictMessage = "The IDE version does not meet the plugin requirements."
                        self.unknownPlugins.append(plugin)
                        toBeRemoved.append(plugin.getPath())
                except Exception as excpt:
                    # Could not successfully call the interface method
                    logging.error(
                        "Error checking IDE version compatibility "
                        "of plugin at " + plugin.getPath() + ". The plugin disabled. Error message: \n" + str(excpt)
                    )
                    plugin.conflictType = CDMPluginManager.BAD_INTERFACE
                    plugin.conflictMessage = "Error checking IDE version compatibility"
                    if category in self.inactivePlugins:
                        self.inactivePlugins[category].append(plugin)
                    else:
                        self.inactivePlugins[category] = [plugin]
                    toBeRemoved.append(plugin.getPath())

        for path in toBeRemoved:
            for category in collectedPlugins:
                for plugin in collectedPlugins[category]:
                    if plugin.getPath() == path:
                        collectedPlugins[category].remove(plugin)
                        break

    def __checkCapabilities(self, collectedPlugins):
        """Reject plugins whose API/capability requirements the host cannot meet (R150)."""
        toBeRemoved = []
        for category in collectedPlugins:
            for plugin in list(collectedPlugins[category]):
                try:
                    getter = getattr(plugin.getObject(), "getCapabilityRequirements", None)
                    spec = getter() if callable(getter) else None
                    result = negotiate_plugin_capabilities(spec)
                    if result.ok:
                        continue
                    logging.warning(
                        "Plugin %s rejected by capability negotiation: %s (path: %s)",
                        plugin.getName(),
                        result.reason,
                        plugin.getPath(),
                    )
                    plugin.conflictType = CDMPluginManager.INCOMPATIBLE_CAPABILITIES
                    plugin.conflictMessage = result.reason
                    self.unknownPlugins.append(plugin)
                    toBeRemoved.append(plugin.getPath())
                except Exception as excpt:
                    logging.error(
                        "Error checking capabilities of plugin at %s. The plugin disabled. Error message:\n%s",
                        plugin.getPath(),
                        str(excpt),
                    )
                    plugin.conflictType = CDMPluginManager.BAD_INTERFACE
                    plugin.conflictMessage = "Error checking plugin capabilities"
                    if category in self.inactivePlugins:
                        self.inactivePlugins[category].append(plugin)
                    else:
                        self.inactivePlugins[category] = [plugin]
                    toBeRemoved.append(plugin.getPath())

        for path in toBeRemoved:
            for category in collectedPlugins:
                for plugin in list(collectedPlugins[category]):
                    if plugin.getPath() == path:
                        collectedPlugins[category].remove(plugin)
                        break

    def __applyDisabledPlugins(self, collectedPlugins):
        """Marks the disabled plugins in accordance to settings"""
        for disabledPlugin in Settings()["disabledPlugins"]:
            # Parse the record
            try:
                conflictType, path, conflictMessage = CDMPluginInfo.parseDisabledLine(disabledPlugin)
            except Exception as excpt:
                logging.warning(str(excpt))
                continue
            norm_path = normalize_plugin_path(path)

            found = False
            for category in collectedPlugins:
                for plugin in list(collectedPlugins[category]):
                    if normalize_plugin_path(plugin.getPath()) == norm_path:
                        found = True
                        plugin.conflictType = conflictType
                        plugin.conflictMessage = conflictMessage
                        if category in self.inactivePlugins:
                            self.inactivePlugins[category].append(plugin)
                        else:
                            self.inactivePlugins[category] = [plugin]
                        collectedPlugins[category].remove(plugin)
                        break
                if found:
                    break

            if not found:
                # Second try - search through the unknown plugins
                for plugin in self.unknownPlugins:
                    if normalize_plugin_path(plugin.getPath()) == norm_path:
                        found = True
                        plugin.conflictType = conflictType
                        plugin.conflictMessage = conflictMessage
                        break

            if not found:
                # Already registered as a policy-skipped stub (R191) — OK.
                if norm_path in self._pendingImportByPath:
                    found = True

            if not found:
                logging.warning(
                    "The disabled plugin at " + path + " has not been found. The information that"
                    " the plugin is disabled will be deleted."
                )

    def __sysVsUserConflicts(self, collectedPlugins):
        """Checks for the system vs user plugin conflicts"""
        for category in collectedPlugins:
            self.__sysVsUserCategoryConflicts(category, collectedPlugins[category])

    def __sysVsUserCategoryConflicts(self, category, plugins):
        """Checks for the system vs user conflicts within one category"""

        def findIndexesByName(plugins, name):
            """Provides the plugin index by name"""
            result = []
            for index in range(len(plugins)):
                if plugins[index].getName() == name:
                    result.append(index)
            return result

        def hasUserPlugin(plugins, indexes):
            """True if has user plugins"""
            for index in indexes:
                if plugins[index].isUser():
                    return True
            return False

        index = 0
        while index < len(plugins):
            name = plugins[index].getName()
            sameNamePluginIndexes = findIndexesByName(plugins, name)
            if hasUserPlugin(plugins, sameNamePluginIndexes):
                # There is at least one user plugin
                # Disable all system plugins
                sameNamePluginIndexes.reverse()
                for checkIndex in sameNamePluginIndexes:
                    if not plugins[checkIndex].isUser():
                        logging.warning(
                            "The system wide plugin '"
                            + name
                            + "' at "
                            + plugins[checkIndex].getPath()
                            + " conflicts with a user plugin with "
                            "the same name. The system wide "
                            "plugin is automatically disabled."
                        )
                        plugins[checkIndex].conflictType = CDMPluginManager.SYSTEM_USER_CONFLICT
                        plugins[checkIndex].conflictMessage = "It conflicts with a user plugin of the same name"
                        if category in self.inactivePlugins:
                            self.inactivePlugins[category].append(plugins[checkIndex])
                        else:
                            self.inactivePlugins[category] = [plugins[checkIndex]]
                        del plugins[checkIndex]
                if plugins[index].getName() == name:
                    index += 1
            else:
                index += 1

    def __categoryConflicts(self, collectedPlugins):
        """Checks for version conflicts within the category"""
        for category in collectedPlugins:
            self.__singleCategoryConflicts(category, collectedPlugins[category])

    def __singleCategoryConflicts(self, category, plugins):
        """Checks a single category for name conflicts"""

        def findIndexesByName(plugins, name):
            """Provides the plugin index by name"""
            result = []
            for index in range(len(plugins)):
                if plugins[index].getName() == name:
                    result.append(index)
            return result

        index = 0
        while index < len(plugins):
            name = plugins[index].getName()
            sameNamePluginIndexes = findIndexesByName(plugins, name)
            if len(sameNamePluginIndexes) == 1:
                # The only plugin of the type. Keep it.
                index += 1
            else:
                # There are many. Check the versions and decide which to remove
                self.__resolveConflictByVersion(category, plugins, sameNamePluginIndexes)

    def __resolveConflictByVersion(self, category, plugins, indexes):
        """Resolves a single version conflict"""
        indexVersion = []
        for index in indexes:
            indexVersion.append((index, Version(plugins[index].getVersion())))

        # Sort basing on version
        indexVersion.sort(key=lambda indexVer: indexVer[1])

        # Disable everything except the last
        highVersion = indexVersion[-1][1]
        toBeDisabled = []
        for index in range(len(indexVersion) - 1):
            pluginIndex = indexVersion[index][0]
            logging.warning(
                "The plugin '"
                + plugins[pluginIndex].getName()
                + "' v."
                + plugins[pluginIndex].getVersion()
                + " at "
                + os.path.normpath(plugins[pluginIndex].getPath())
                + " conflicts with another plugin of the same name "
                "and version " + str(highVersion) + ". The former is disabled automatically."
            )
            toBeDisabled.append(pluginIndex)

        # Move the disabled to the inactive list
        toBeDisabled.sort()
        toBeDisabled.reverse()
        for index in toBeDisabled:
            plugins[index].conflictType = CDMPluginManager.VERSION_CONFLICT
            plugins[index].conflictMessage = "It conflicts with another plugin of the same name"
            if category in self.inactivePlugins:
                self.inactivePlugins[category].append(plugins[index])
            else:
                self.inactivePlugins[category] = [plugins[index]]
            del plugins[index]

    def saveDisabledPlugins(self):
        """Saves the disabled plugins info into the settings"""
        value = []
        for category in self.inactivePlugins:
            for plugin in self.inactivePlugins[category]:
                line = plugin.getDisabledLine()
                if line is not None:
                    value.append(line)
        for plugin in self.unknownPlugins:
            line = plugin.getDisabledLine()
            if line is not None:
                value.append(line)
        Settings()["disabledPlugins"] = value

    def checkConflict(self, cdmPlugin):
        """Checks for the conflict and returns a message if so.

        If there is no conflict then returns None
        """
        # R191: materialize deferred imports before touching plugin_object.
        try:
            self.materializePlugin(cdmPlugin)
        except Exception as exc:
            return f"Error importing plugin: {exc}"

        # First, check the base class
        baseClasses = getBaseClassNames(cdmPlugin.getObject())
        category = None
        for registeredCategory in CATEGORIES:
            if registeredCategory in baseClasses:
                category = registeredCategory
                break
        if category is None:
            return "Plugin category is not recognised"

        # Second, IDE version compatibility
        from utils.globals import GlobalData

        try:
            ideVer = GlobalData().version
            if not cdmPlugin.getObject().isIDEVersionCompatible(ideVer):
                return "Plugin requires the other IDE version"
        except Exception:
            # Could not successfully call the interface method
            return "Error checking IDE version compatibility"

        # Second-b, API / capability negotiation (R150)
        try:
            getter = getattr(cdmPlugin.getObject(), "getCapabilityRequirements", None)
            spec = getter() if callable(getter) else None
            result = negotiate_plugin_capabilities(spec)
            if not result.ok:
                return result.reason
        except Exception:
            return "Error checking plugin capabilities"

        # Third, the other plugin with the same name is active
        if category in self.activePlugins:
            for plugin in self.activePlugins[category]:
                if plugin.getName() == cdmPlugin.getName():
                    return "Another plugin of the same name is active"

        return None

    def sendPluginActivated(self, plugin):
        """Emits the signal with the corresponding plugin"""
        self.sigPluginActivated.emit(plugin)
        plugin.getObject().pluginLogMessage.connect(self.__onPluginLogMessage)

    def sendPluginDeactivated(self, plugin):
        """Emits the signal with the corresponding plugin"""
        plugin.getObject().pluginLogMessage.disconnect(self.__onPluginLogMessage)
        self.sigPluginDeactivated.emit(plugin)

    @staticmethod
    def __onPluginLogMessage(logLevel, message):
        """Triggered when a plugin message is received"""
        logging.log(logLevel, str(message))


class CDMPluginInfo:
    """Holds info about a single plugin"""

    def __init__(self, pluginInfo):
        """The pluginInfo comes from yapsy"""
        # yapsy.PluginInfo
        self.__info = pluginInfo
        self.__isUser = self.__isUserPlugin()
        self.isEnabled = False
        # See CDMPluginManager constants
        self.conflictType = CDMPluginManager.NO_CONFLICT
        # One line message for UI/log
        self.conflictMessage = ""
        self.categoryName = None

    def isUser(self):
        """True if it is a user plugin"""
        return self.__isUser

    def __isUserPlugin(self):
        """True if it is a user plugin"""
        return self.getPath().startswith(SETTINGS_DIR)

    def getDisabledLine(self):
        """Used for the setting file"""
        if self.isEnabled is None or self.isEnabled:
            return None
        return str(self.conflictType) + ":::" + normalize_plugin_path(self.__info.path) + ":::" + self.conflictMessage

    @staticmethod
    def parseDisabledLine(configLine):
        """Parser the config line and returns a tuple"""
        parts = configLine.split(":::", 2)
        if len(parts) != 3:
            raise ValueError("Incorrect disabled plugin description: " + configLine)
        # (conflictType, path, conflictMessage)
        return (int(parts[0]), parts[1], parts[2])

    def getObject(self):
        """Provides a reference to the plugin object"""
        return self.__info.plugin_object

    def getPath(self):
        """Provides the plugin path"""
        return str(self.__info.path)

    def getName(self):
        """Provides the plugin name"""
        return str(self.__info.name)

    def getVersion(self):
        """Provides the plugin version"""
        return self.__info.details.get("Documentation", "Version")

    def getAuthor(self):
        """Provides the author name"""
        return self.__info.details.get("Documentation", "Author")

    def getDescription(self):
        """Provides the description"""
        return self.__info.details.get("Documentation", "Description")

    def getWebsite(self):
        """Provides the website"""
        return self.__info.details.get("Documentation", "Website")

    def getCopyright(self):
        """Provides the copyright"""
        return self.__info.details.get("Documentation", "Copyright")

    def getDetails(self):
        """Provides additional values from from the description section"""
        result = {}
        for name, value in self.__info.details.items("Documentation"):
            if name.lower() in ["version", "author", "description", "website", "copyright"]:
                continue
            result[name] = value
        return result

    def disable(self, conflictType=CDMPluginManager.USER_DISABLED, conflictMessage=""):
        """Disables the plugin"""
        self.isEnabled = False
        self.conflictType = conflictType
        self.conflictMessage = conflictMessage

        obj = self.getObject()
        if obj is not None and getattr(obj, "is_activated", False):
            if self.categoryName == "VersionControlSystemInterface":
                from utils.globals import GlobalData

                GlobalData().mainWindow.dismissVCSPlugin(self)
            obj.deactivate()

    def enable(self):
        """Enables the plugin"""
        from utils.globals import GlobalData

        manager = GlobalData().pluginManager
        manager.materializePlugin(self)

        if not self.getObject().is_activated:
            self.getObject().activate(Settings(), GlobalData())

        self.isEnabled = True
        self.conflictType = CDMPluginManager.NO_CONFLICT
        self.conflictMessage = ""


def normalize_plugin_path(path: str) -> str:
    """Canonical plugin path for policy matching (R191)."""
    if not path:
        return ""
    normalized = os.path.normpath(os.path.abspath(str(path)))
    # yapsy may leave a trailing ``/.`` when Module = .
    if normalized.endswith(os.sep + "."):
        normalized = os.path.dirname(normalized)
    return normalized


def guess_plugin_category_from_source(module_filepath: str) -> str | None:
    """Infer plugin category from source text without importing (R191).

    Reads ``__init__.py`` / ``.py`` and looks for known interface names.
    """
    candidates = []
    base = module_filepath
    if base.endswith("__init__"):
        candidates.append(base + ".py")
        candidates.append(os.path.join(os.path.dirname(base), "__init__.py"))
    else:
        candidates.append(base + ".py")
        candidates.append(base)
        candidates.append(os.path.join(base, "__init__.py"))

    text = ""
    for path in candidates:
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as handle:
                    text = handle.read()
            except OSError:
                continue
            break
    if not text:
        return None
    # Prefer the more specific VCS interface when both appear (unlikely).
    if "VersionControlSystemInterface" in text:
        return "VersionControlSystemInterface"
    if "WizardInterface" in text:
        return "WizardInterface"
    return None


def getBaseClassNames(inst):
    """Provides a list of base class names for the given instance"""
    baseNames = []

    def baseClassNames(inst, names):
        """Recursive retriever"""
        if hasattr(inst, "__bases__"):
            container = inst.__bases__
        else:
            container = inst.__class__.__bases__
        for base in container:
            names.append(base.__name__)
            if base.__name__ != "object":
                baseClassNames(base, names)
        return

    baseClassNames(inst, baseNames)
    return baseNames
