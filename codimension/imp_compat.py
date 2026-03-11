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

"""Compatibility shim for deprecated imp module (removed in Python 3.12).

Provides imp.load_module, imp.PKG_DIRECTORY, imp.PY_SOURCE for yapsy
and other dependencies that still rely on the removed imp module.
"""

from __future__ import annotations

import importlib.util
import os
import sys

# Constants matching the deprecated imp module (Python 3.10 docs)
PY_SOURCE = 1
PY_COMPILED = 2
C_EXTENSION = 3
PKG_DIRECTORY = 5
C_BUILTIN = 6
PY_FROZEN = 7


def load_module(name: str, file_obj, pathname: str, description: tuple) -> object:
    """Load a module from file or package directory (imp.load_module replacement).

    Args:
        name: Full module name.
        file_obj: Open file object or None for packages.
        pathname: Path to the file or package directory.
        description: Tuple (suffix, mode, type) e.g. ("py", "r", PY_SOURCE).

    Returns:
        Loaded module object.
    """
    mod_type = description[2] if len(description) > 2 else PY_SOURCE

    if file_obj is None and mod_type == PKG_DIRECTORY:
        # Package: pathname is directory, load __init__.py
        init_path = os.path.join(pathname, "__init__.py")
        spec = importlib.util.spec_from_file_location(name, init_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load package {name} from {pathname}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module

    if file_obj is not None and mod_type == PY_SOURCE:
        # Single .py file (pathname is used; file_obj is not needed by importlib)
        spec = importlib.util.spec_from_file_location(name, pathname)  # type: ignore
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load module {name} from {pathname}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module

    raise ImportError(f"Unsupported module type {mod_type} for {name}")
