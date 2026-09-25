# -*- coding: utf-8 -*-
#
# codimension - graphics python two-way code editor and analyzer
# Copyright (C) 2010-2017 Sergey Satskiy <sergey.satskiy@gmail.com>
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

"""import utility functions"""

# pylint: disable=W0702
# pylint: disable=W0703

import importlib
import os
import os.path
import sys
from importlib.machinery import PathFinder
from importlib.util import find_spec as _stdlib_find_spec

from cdmpyparser import getBriefModuleInfoFromMemory

from .fileutils import isPythonFile
from .globals import GlobalData
from .run import getProjectPythonPath, getVenvSitePackages


def getImportsList(fileContent):
    """Parses a python file and provides a list imports in it"""
    info = getBriefModuleInfoFromMemory(fileContent)
    return info.imports


def getImportsInLine(fileContent, lineNumber):
    """Provides a list of imports in in the given import line"""
    imports = []
    importsWhat = []
    info = getBriefModuleInfoFromMemory(str(fileContent))
    for importObj in info.imports:
        if importObj.line == lineNumber:
            if importObj.name not in imports:
                imports.append(importObj.name)
            for whatObj in importObj.what:
                if whatObj.name not in importsWhat:
                    importsWhat.append(whatObj.name)
    return imports, importsWhat


def __scanDir(prefix, path, progress_callback=None):
    """Recursive scan for modules.

    progress_callback: optional ``callable(message: str)`` for UI/CLI progress.
    Qt event pumping belongs in the caller (UI layer), not here.
    """
    if progress_callback is not None:
        progress_callback("Scanning " + path + "...")

    result = []
    for item in os.listdir(path):
        if item in [".svn", ".cvs", ".git", ".hg"]:
            continue
        if os.path.isdir(path + item):
            result += __scanDir(prefix + item + ".", path + item + os.path.sep, progress_callback)
            continue

        if not isPythonFile(path + item):
            continue
        if item.startswith("__init__."):
            if prefix != "":
                result.append(prefix[:-1])
            continue

        nameParts = item.split(".")
        result.append(prefix + nameParts[0])
    return result


def buildDirModules(path, progress_callback=None):
    """Builds a list of modules how they may appear in the import statements.

    progress_callback: optional ``callable(message: str)``. Callers that need
    a responsive Qt UI should pump events inside their own callback.
    """
    abspath = os.path.abspath(path)
    if not os.path.exists(abspath):
        raise Exception("Cannot build list of modules for not existed dir (" + path + ")")
    if not os.path.isdir(abspath):
        raise Exception("Cannot build list of modules. The path " + path + " is not a directory.")
    if not abspath.endswith(os.path.sep):
        abspath += os.path.sep
    return __scanDir("", abspath, progress_callback)


def isImportModule(info, name):
    """Returns the list of really matched modules"""
    matches = []
    for item in info.imports:
        # We are interested here in those which import a module
        if item.what:
            continue

        if item.alias == "":
            if item.name == name:
                if name not in matches:
                    matches.append(name)
        else:
            if item.alias == name:
                if item.name not in matches:
                    matches.append(item.name)
    return matches


def isImportedObject(info, name):
    """Returns a list of matched modules with the real name"""
    matches = []
    for item in info.imports:
        # We are interested here in those which import an object
        if not item.what:
            continue

        for whatItem in item.what:
            if whatItem.alias == "":
                if whatItem.name == name:
                    if name not in matches:
                        matches.append([item.name, name])
            else:
                if whatItem.alias == name:
                    if whatItem.name not in matches:
                        matches.append([item.name, whatItem.name])
    return matches


class ImportResolution:
    def __init__(self, importObj, itemIndex, builtIn, path, what, message=None):
        # More or less input: import object and a 0-based index of the imported
        # items if so. Index could be None if there is no what list.
        # Example when index is not None:
        # from x import y, z
        # and y and z are should have been resolved as files
        self.importObj = importObj
        self.itemIndex = itemIndex  # Index is None for most of the cases
        # though

        # Resolution result
        self.path = path  # Path to the resolved file
        # None for built-in and not resolved
        self.what = what  # A list of names imported from it
        self.builtIn = builtIn  # True if it is a built-in module
        self.errMessage = message  # Error message if not resolved

    def isResolved(self):
        """True if the import is resolved"""
        return self.path is not None or self.builtIn

    def getVisibleName(self):
        """If it was a submodule then the name is combined"""
        name = self.importObj.name
        if self.itemIndex is not None:
            # ``Import.what`` holds ``ImportWhat`` objects (brief model), not bare strings.
            what_item = self.importObj.what[self.itemIndex]
            what_name = what_item if isinstance(what_item, str) else what_item.name
            name += "." + what_name
        return name


def __getBaseSysPath():
    """Returns sys.path for import resolution (original or current as fallback)."""
    orig = GlobalData().originalSysPath
    if orig and len(orig) > 0:
        return list(orig)
    return list(sys.path)


def __resolution_from_spec(importObj, spec, *, what=None, item_index=None):
    """Build a resolved ``ImportResolution`` from a ``ModuleSpec``, or ``None``.

    Python 3.11+ ships many stdlib modules as frozen (``origin='frozen'``,
    ``has_location=False``). Treating those as unresolved produced false
    WARNINGs for ``import os`` / ``import io`` on import diagrams.

    R281: PEP 420 namespace packages (no ``__init__.py``) expose
    ``submodule_search_locations`` without ``has_location``; treat them as
    resolved so project trees like ``core/`` are not false-unresolved.
    """
    if spec is None:
        return None
    origin = getattr(spec, "origin", None)
    if origin in ("frozen", "built-in"):
        return ImportResolution(importObj, item_index, True, None, what)
    if spec.has_location and origin:
        return ImportResolution(importObj, item_index, False, origin, what)
    locations = getattr(spec, "submodule_search_locations", None)
    if locations is not None:
        loc = None
        try:
            loc = os.path.abspath(str(next(iter(locations))))
        except StopIteration:
            loc = None
        return ImportResolution(importObj, item_index, False, loc, what)
    return None


def __find_spec(name: str, search_paths: list[str] | None = None):
    """Resolve a module spec, preferring ``search_paths`` via PathFinder (R281).

    ``importlib.util.find_spec`` consults ``sys.modules`` and editable
    ``meta_path`` finders first, so IDE packages named ``utils`` / ``core``
    shadow the opened project. ``PathFinder.find_spec(name, search_paths)``
    only walks the given directories.

    Dotted names under PEP 420 namespace packages need a piecewise walk:
    ``PathFinder.find_spec('core.control_adapter', roots)`` returns ``None``.
    """
    if search_paths:
        try:
            spec = PathFinder.find_spec(name, search_paths)
            if spec is not None:
                return spec
            parts = name.split(".")
            if len(parts) > 1:
                locations = list(search_paths)
                spec = None
                for index, part in enumerate(parts):
                    spec = PathFinder.find_spec(part, locations)
                    if spec is None:
                        break
                    if index == len(parts) - 1:
                        return spec
                    locations = list(getattr(spec, "submodule_search_locations", None) or [])
                    if not locations:
                        break
        except Exception:
            pass
    return _stdlib_find_spec(name)


def __resolution_sys_path(baseAndProjectPaths):
    """Project / venv paths must precede the IDE ``sys.path`` (R281).

    Codimension's editable install exposes top-level names such as ``utils``
    and ``core``. Putting the IDE path first made ``find_spec`` bind those
    instead of same-named packages inside the opened project.
    """
    return list(baseAndProjectPaths) + __getBaseSysPath()


def __path_is_under(path: str, root: str) -> bool:
    """True when ``path`` is ``root`` or a descendant (realpath)."""
    if not path or not root:
        return False
    real = os.path.realpath(path)
    base = os.path.realpath(root)
    if not base.endswith(os.sep):
        base = base + os.sep
    return real == os.path.realpath(root) or real.startswith(base)


def __evict_shadowing_modules(top_levels, project_dir: str) -> dict:
    """Remove IDE-loaded packages that would shadow project packages (R281).

    ``importlib.util.find_spec`` returns entries already in ``sys.modules``.
    After the IDE imported ``utils`` / ``core``, project modules with the same
    top-level names never resolve. Evict only names that also exist under the
    project root (avoid touching third-party modules such as ``numpy``).
    """
    if not project_dir or not top_levels:
        return {}
    local = projectLocalPackageNames(project_dir)
    collide = {name for name in top_levels if name and name in local}
    if not collide:
        return {}
    saved: dict = {}
    for name in collide:
        keys = [key for key in list(sys.modules) if key == name or key.startswith(name + ".")]
        for key in keys:
            mod = sys.modules.get(key)
            if mod is None:
                continue
            origin = getattr(mod, "__file__", None) or ""
            if origin and __path_is_under(origin, project_dir):
                continue
            paths = getattr(mod, "__path__", None)
            if paths and any(__path_is_under(str(entry), project_dir) for entry in paths):
                continue
            saved[key] = sys.modules.pop(key)
    return saved


def __discover_third_party_src_dirs(project_dir: str) -> list[str]:
    """Return ``third_party/<name>/src`` layout roots (src-layout vendors)."""
    extras: list[str] = []
    root = os.path.join(project_dir, "third_party")
    if not os.path.isdir(root):
        return extras
    try:
        for name in sorted(os.listdir(root)):
            src = os.path.join(root, name, "src")
            if os.path.isdir(src):
                extras.append(src)
    except OSError:
        return extras
    return extras


def projectLocalPackageNames(project_dir: str) -> set[str]:
    """Top-level package/module names that live under the project root (R281)."""
    if not project_dir or not os.path.isdir(project_dir):
        return set()
    names: set[str] = set()
    roots = [project_dir] + __discover_third_party_src_dirs(project_dir)
    for root in roots:
        try:
            for entry in os.listdir(root):
                if entry.startswith(".") or not entry.isidentifier():
                    continue
                full = os.path.join(root, entry)
                if os.path.isfile(full) and entry.endswith(".py"):
                    names.add(entry[:-3])
                    continue
                if not os.path.isdir(full):
                    continue
                if os.path.isfile(os.path.join(full, "__init__.py")):
                    names.add(entry)
                    continue
                # Namespace-style dirs (``.py`` files, no ``__init__.py``).
                try:
                    if any(
                        name.endswith(".py") and os.path.isfile(os.path.join(full, name)) for name in os.listdir(full)
                    ):
                        names.add(entry)
                except OSError:
                    continue
        except OSError:
            continue
    return names


def __resolveImport(importObj, baseAndProjectPaths, result):
    """Resolves imports like: 'import x'"""

    # import x.y
    # Could be (priority wise)
    # I:   <dir>/x/y/__init__.py
    # II:  <dir>/x/y.py

    if importObj.name in sys.builtin_module_names:
        result.append(ImportResolution(importObj, None, True, None, None))
        return

    oldSysPath = sys.path
    sys.path = __resolution_sys_path(baseAndProjectPaths)

    try:
        spec = __find_spec(importObj.name, baseAndProjectPaths)
        resolved = __resolution_from_spec(importObj, spec)
        if resolved is not None:
            result.append(resolved)
            return
    except Exception:
        pass
    finally:
        sys.path = oldSysPath

    result.append(
        ImportResolution(
            importObj,
            None,
            False,
            None,
            None,
            "Could not resolve 'import " + importObj.name + "' at line " + str(importObj.line),
        )
    )


def __resolveFrom(importObj, importName, result, search_paths: list[str] | None = None):
    """Common resolution imports like 'from [.]x import y.

    When ``search_paths`` is set (absolute project resolve), use PathFinder on
    those directories before the IDE-aware ``find_spec`` (R281).
    """
    what_names = [what.name for what in importObj.what]
    if importObj.name in sys.builtin_module_names:
        result.append(ImportResolution(importObj, None, True, None, what_names))
        return

    try:
        spec = __find_spec(importName, search_paths)
        resolved = __resolution_from_spec(importObj, spec, what=what_names)
        if resolved is not None:
            result.append(resolved)
            return

        if spec is None:
            pass
        elif spec.loader is not None:
            # Found a loader but not a file/frozen origin we understand.
            result.append(
                ImportResolution(
                    importObj,
                    None,
                    False,
                    None,
                    None,
                    "Could not resolve 'from " + importObj.name + " import ...' at line " + str(importObj.line),
                )
            )
            return
        elif spec.submodule_search_locations:
            # Namespace / package without a single file — resolve each name.
            for index, what in enumerate(importObj.what):
                impName = importName + "." + what.name
                found = False
                try:
                    sub_spec = __find_spec(impName, search_paths)
                    sub_resolved = __resolution_from_spec(importObj, sub_spec, item_index=index)
                    if sub_resolved is not None:
                        result.append(sub_resolved)
                        found = True
                except Exception:
                    pass
                if not found:
                    result.append(
                        ImportResolution(
                            importObj,
                            index,
                            False,
                            None,
                            None,
                            "Could not resolve 'from "
                            + importObj.name
                            + " import "
                            + what.name
                            + "' at line "
                            + str(importObj.line),
                        )
                    )
            return
    except Exception:
        pass

    result.append(
        ImportResolution(
            importObj,
            None,
            False,
            None,
            None,
            "Could not resolve 'from " + importObj.name + " import ...' at line " + str(importObj.line),
        )
    )


def __resolveFromImport(importObj, basePath, baseAndProjectPaths, result):
    """Resolves imports like: 'from x import y'"""

    # from x.y import z
    # Could be (priority wise)
    # I:    <dir>/x/y/__init__.py  -> z
    # II:   <dir>/x/y.py  -> z
    # III:  <dir>/x/y/z/__init__.py
    # IV:   <dir>/x/y/z.py

    oldSysPath = sys.path
    sys.path = __resolution_sys_path(baseAndProjectPaths)

    __resolveFrom(importObj, importObj.name, result, search_paths=baseAndProjectPaths)

    sys.path = oldSysPath


def __resolveRelativeImport(importObj, basePath, result):
    """Resolves imports like: 'from ..x import y'"""

    # from ...x.y import z
    # Could be (priority wise)
    # I:    <dir>/x/y/__init__.py  -> z
    # II:   <dir>/x/y.py  -> z
    # III:  <dir>/x/y/z/__init__.py
    # IV:   <dir>/x/y/z.py

    if basePath is None:
        result.append(
            ImportResolution(
                importObj,
                None,
                False,
                None,
                None,
                "Could not resolve 'from "
                + importObj.name
                + " import ...' at line "
                + str(importObj.line)
                + " because the editing buffer has not been saved yet",
            )
        )
    else:
        path = basePath
        current = importObj.name[1:]
        error = False
        while current.startswith("."):
            if not path:
                error = True
                break
            current = current[1:]
            path = os.path.dirname(path)
        if error:
            result.append(
                ImportResolution(
                    importObj,
                    None,
                    False,
                    None,
                    None,
                    "Could not resolve 'from " + importObj.name + " import ...' at line " + str(importObj.line),
                )
            )
            return

        if not path:
            path = os.path.sep  # reached the root directory

        # This is a relative import so only one path needs to be searched
        oldSysPath = sys.path
        sys.path = [path]

        __resolveFrom(importObj, current, result)

        sys.path = oldSysPath


def getImportResolutions(fileName, imports):
    """Resolves a list of imports.

    fileName: the file where the imports come from
    imports: a list of the Import classes coming from the cdmpyparser module

    return: [ImportResolution instance, ...]
    """
    result = []

    origImporterCacheKeys = set(sys.path_importer_cache.keys())
    origSysModulesKeys = set(sys.modules.keys())

    basePath = os.path.dirname(fileName) if fileName else None
    # R281: project root and vendor src dirs first; file directory last so a
    # nested ``interceptor/vision`` cannot shadow top-level ``vision/``.
    baseAndProjectPaths: list[str] = []
    project_dir = ""

    project = GlobalData().project
    if project.isLoaded():
        project_dir = project.getProjectDir() or ""
        if project_dir and project_dir not in baseAndProjectPaths:
            baseAndProjectPaths.append(project_dir)
        for importDir in project.getImportDirsAsAbsolutePaths():
            if importDir not in baseAndProjectPaths:
                baseAndProjectPaths.append(importDir)
        for vendor_src in __discover_third_party_src_dirs(project_dir.rstrip(os.sep)):
            if vendor_src not in baseAndProjectPaths:
                baseAndProjectPaths.append(vendor_src)
        # Add project venv site-packages for third-party imports (numpy, etc.)
        proj_python = getProjectPythonPath(project)
        site_pkg = getVenvSitePackages(proj_python)
        if site_pkg and site_pkg not in baseAndProjectPaths:
            baseAndProjectPaths.append(site_pkg)

    if basePath and basePath not in baseAndProjectPaths:
        baseAndProjectPaths.append(basePath)

    top_levels = set()
    for importObj in imports:
        top = _top_level_import_name(importObj.name)
        if top:
            top_levels.add(top)
    saved_modules = __evict_shadowing_modules(top_levels, project_dir.rstrip(os.sep))

    try:
        for importObj in imports:
            if not importObj.what:
                # case 1: import x1, y1
                __resolveImport(importObj, baseAndProjectPaths, result)
            elif not importObj.name.startswith("."):
                # case 2: from i2 import x2, y2
                __resolveFromImport(importObj, basePath, baseAndProjectPaths, result)
            else:
                # case 3: from .i3 import x3, y3
                #      or from . import x4, y4
                __resolveRelativeImport(importObj, basePath, result)
    finally:
        sys.modules.update(saved_modules)

    importlib.invalidate_caches()

    newImporterCacheKeys = set(sys.path_importer_cache.keys())
    diff = newImporterCacheKeys - origImporterCacheKeys
    for key in diff:
        del sys.path_importer_cache[key]

    newSysModulesKeys = set(sys.modules.keys())
    diff = newSysModulesKeys - origSysModulesKeys
    for key in diff:
        del sys.modules[key]

    return result


def resolveImports(fileName, imports):
    """Resolves a list of imports. Legacy function.

    fileName: the file where the imports come from
    imports: a list of the Import classes coming from the cdmpyparser module

    return: ([resolved imports], [errors])
    Each resolved import is a triple [name, path, [what imported]]
        path could be .py or .so or None or 'built-in'
    errors is a list of strings
    """
    result = []
    errors = []
    abs_file = os.path.abspath(fileName) if fileName else ""
    for resolution in getImportResolutions(fileName, imports):
        if resolution.isResolved():
            if resolution.builtIn:
                path = "built-in"
            else:
                path = resolution.path
            if resolution.what is None:
                what = []
            else:
                what = resolution.what
            result.append((resolution.getVisibleName(), path, what))
        else:
            msg = resolution.errMessage or "Could not resolve import"
            # R177: prefix with path:line: so LogViewer can navigate on double-click.
            if abs_file and not msg.startswith(abs_file + ":"):
                line = getattr(resolution.importObj, "line", None) or 1
                try:
                    line = int(line)
                except (TypeError, ValueError):
                    line = 1
                if line < 1:
                    line = 1
                msg = f"{abs_file}:{line}: {msg}"
            errors.append(msg)

    return result, errors


# Standard library modules (common). Unresolved third-party suggests missing deps.
_STDLIB_MODULES = frozenset(
    {
        "os",
        "io",
        "sys",
        "re",
        "json",
        "math",
        "datetime",
        "time",
        "logging",
        "pathlib",
        "subprocess",
        "argparse",
        "collections",
        "itertools",
        "functools",
        "typing",
        "abc",
        "copy",
        "hashlib",
        "uuid",
        "tempfile",
        "shutil",
        "glob",
        "socket",
        "threading",
        "multiprocessing",
        "asyncio",
        "contextlib",
        "unittest",
        "doctest",
        "pdb",
        "traceback",
        "warnings",
        "importlib",
        "configparser",
        "csv",
        "xml",
        "html",
        "email",
        "urllib",
        "http",
        "sqlite3",
        "pickle",
        "shelve",
        "getpass",
        "platform",
        "errno",
        "ctypes",
    }
)


def _top_level_import_name(import_name):
    """Return a pip-installable top-level name, or None for relative imports."""
    if not import_name or import_name.startswith("."):
        return None
    top = import_name.split(".", 1)[0]
    if not top or not top.isidentifier():
        return None
    return top


def getUnresolvedPackageNames(errors, *, project_dir: str | None = None):
    """Extract top-level package names from resolveImports error messages.

    Returns set of names (e.g. {'numpy', 'cryptography', 'pymavlink'}).
    Excludes known stdlib modules, relative imports, and (R281) packages that
    already exist as directories under ``project_dir`` (not pip-installable).
    """
    import re

    names = set()
    for err in errors:
        m = re.search(r"'import ([^']+)'", err)
        if m:
            top = _top_level_import_name(m.group(1))
            if top and top not in _STDLIB_MODULES:
                names.add(top)
            continue
        m = re.search(r"'from ([^']+) import", err)
        if m:
            top = _top_level_import_name(m.group(1))
            if top and top not in _STDLIB_MODULES:
                names.add(top)
    if project_dir:
        names -= projectLocalPackageNames(project_dir)
    return names


def _except_handler_names(handler) -> set[str]:
    """Collect exception class names referenced by an ``except`` handler."""
    import ast

    names: set[str] = set()

    def _walk(node) -> None:
        if node is None:
            return
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Tuple):
            for elt in node.elts:
                _walk(elt)

    _walk(handler.type)
    return names


def _import_names_from_stmt(stmt) -> set[str]:
    """Top-level package names from a single Import / ImportFrom statement."""
    import ast

    names: set[str] = set()
    if isinstance(stmt, ast.Import):
        for alias in stmt.names:
            top = _top_level_import_name(alias.name)
            if top:
                names.add(top)
    elif isinstance(stmt, ast.ImportFrom):
        if getattr(stmt, "level", 0):
            return names
        if stmt.module:
            top = _top_level_import_name(stmt.module)
            if top:
                names.add(top)
    return names


def collectOptionalImportNames(source: str) -> set[str]:
    """Return top-level names imported only under ``try``/``except ImportError``.

    Used so Generate requirements / Update VENV do not treat optional local
    extensions (e.g. ``import native`` behind ImportError) as pip packages (R278).
    """
    import ast

    if not source:
        return set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()

    optional: set[str] = set()
    import_error_names = {"ImportError", "ModuleNotFoundError"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        if not any(_except_handler_names(handler) & import_error_names for handler in node.handlers):
            continue
        for stmt in node.body:
            optional |= _import_names_from_stmt(stmt)
    return optional


def collectOptionalImportNamesFromFiles(filesList) -> set[str]:
    """Union of optional import names across project Python files."""
    from .config import DEFAULT_ENCODING
    from .fileutils import isPythonFile

    optional: set[str] = set()
    for item in filesList:
        if item.endswith(os.sep) or not isPythonFile(item):
            continue
        try:
            with open(item, "r", encoding=DEFAULT_ENCODING, errors="replace") as handle:
                optional |= collectOptionalImportNames(handle.read())
        except OSError:
            continue
    return optional


def filterRequirementLines(text: str, skip_packages) -> tuple[str, list[str]]:
    """Drop requirements lines whose package name is in ``skip_packages``.

    Returns ``(filtered_text, skipped_package_names)``.
    """
    skip = {str(name).lower() for name in (skip_packages or ()) if name}
    if not skip:
        return text, []
    kept: list[str] = []
    skipped: list[str] = []
    for line in text.splitlines(keepends=True):
        pkg = _parseRequirementsPackageName(line)
        if pkg and pkg.lower() in skip:
            skipped.append(pkg)
            continue
        kept.append(line)
    return "".join(kept), skipped


def prepareRequirementFilesForInstall(requirement_files, skip_packages, *, temp_dir: str):
    """Write filtered requirement files, omitting packages in ``skip_packages``.

    Returns ``(paths_for_pip, skipped_package_names)``. Empty filtered files are
    dropped so ``pip install -r`` is not invoked with a blank requirements file.
    """
    from .config import DEFAULT_ENCODING

    skip = {str(name) for name in (skip_packages or ()) if name}
    if not requirement_files:
        return [], []
    if not skip:
        return list(requirement_files), []

    os.makedirs(temp_dir, exist_ok=True)
    prepared: list[str] = []
    skipped_all: list[str] = []
    for index, path in enumerate(requirement_files):
        try:
            with open(path, "r", encoding=DEFAULT_ENCODING, errors="replace") as handle:
                original = handle.read()
        except OSError:
            prepared.append(path)
            continue
        filtered, skipped = filterRequirementLines(original, skip)
        skipped_all.extend(skipped)
        if not skipped:
            prepared.append(path)
            continue
        if not any(line.strip() and not line.strip().startswith("#") for line in filtered.splitlines()):
            continue
        out_path = os.path.join(temp_dir, f"requirements_filtered_{index}.txt")
        with open(out_path, "w", encoding=DEFAULT_ENCODING) as handle:
            handle.write(filtered)
        prepared.append(out_path)
    # Preserve order, unique skip names
    seen: set[str] = set()
    unique_skipped: list[str] = []
    for name in skipped_all:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        unique_skipped.append(name)
    return prepared, unique_skipped


def getRequirementsHint(projectDir, unresolvedPackages):
    """Return hint string for missing dependencies, or None."""
    packages = sorted({name for name in unresolvedPackages if name})
    if not projectDir or not packages:
        return None
    reqPath = os.path.join(projectDir, "requirements.txt")
    if os.path.isfile(reqPath):
        return (
            "Unresolved imports (possibly missing dependencies): "
            + ", ".join(packages)
            + ". Consider: pip install -r requirements.txt"
        )
    return (
        "Unresolved imports (possibly missing dependencies): "
        + ", ".join(packages)
        + ". Consider: pip install "
        + " ".join(packages)
    )


def generateRequirementsFromProject(filesList, progressCallback=None):
    """Scan project Python files for unresolved imports and collect third-party package names.

    Args:
        filesList: Iterable of file/dir paths from project (full paths; dirs end with sep).
        progressCallback: Optional callable(current, total, message) for progress updates.

    Returns:
        (packages_set, error_count): Set of top-level package names, count of resolved errors.
        Optional ``try``/``except ImportError`` imports are excluded (R278).
    """
    from .fileutils import isPythonFile

    allErrors = []
    optionalNames: set[str] = set()
    pythonFiles = []
    for item in filesList:
        if item.endswith(os.sep):
            continue
        if isPythonFile(item):
            pythonFiles.append(item)

    total = len(pythonFiles)
    for idx, fName in enumerate(pythonFiles):
        if progressCallback:
            progressCallback(idx, total, "Scanning " + os.path.basename(fName) + "...")
        try:
            info = GlobalData().briefModinfoCache.get(fName)
            _, errors = resolveImports(fName, info.imports)
            allErrors.extend(errors)
        except Exception:
            pass
        try:
            from .config import DEFAULT_ENCODING

            with open(fName, "r", encoding=DEFAULT_ENCODING, errors="replace") as handle:
                optionalNames |= collectOptionalImportNames(handle.read())
        except OSError:
            pass

    project_dir = None
    project = GlobalData().project
    if project is not None and project.isLoaded():
        project_dir = project.getProjectDir()
    packages = getUnresolvedPackageNames(allErrors, project_dir=project_dir) - optionalNames
    return packages, len(allErrors)


def _parseRequirementsPackageName(line):
    """Extract package name from a requirements line (e.g. 'numpy>=1.0' -> 'numpy')."""
    import re

    line = line.strip().split("#")[0].strip()
    if not line or line.startswith("-"):
        return None
    match = re.match(r"^([a-zA-Z0-9_-]+)", line)
    return match.group(1).lower() if match else None


def writeRequirementsFile(path, packages, mode="w"):
    """Write package names to requirements.txt.

    Args:
        path: Full path to requirements.txt.
        packages: Iterable of package names (e.g. {'numpy', 'requests'}).
        mode: 'w' to overwrite, 'a' to append (only new packages).

    Returns:
        Number of lines written.
    """
    from .config import DEFAULT_ENCODING

    sortedPkgs = sorted(packages)
    if not sortedPkgs:
        return 0

    existing = set()
    if mode == "a" and os.path.isfile(path):
        with open(path, "r", encoding=DEFAULT_ENCODING) as f:
            for line in f:
                pkg = _parseRequirementsPackageName(line)
                if pkg:
                    existing.add(pkg)
        sortedPkgs = [p for p in sortedPkgs if p.lower() not in existing]

    if not sortedPkgs:
        return 0

    with open(path, mode, encoding=DEFAULT_ENCODING) as f:
        for pkg in sortedPkgs:
            f.write(pkg + "\n")
    return len(sortedPkgs)
