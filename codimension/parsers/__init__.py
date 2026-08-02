# -*- coding: utf-8 -*-
#
# codimension - parsers package
# Copyright (C) 2010-2025  Sergey Satskiy <sergey.satskiy@gmail.com>
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

"""Parsers package - fallback implementations for Python 3.11+.

When cdmpyparser/cdmcfparser C extensions are unavailable (node.h removed
in Python 3.10+), provides pure-Python ast-based implementations.

Module names ``cdmpyparser`` / ``cdmcfparser`` are preserved (product API).
T073: all aliases point at the same module object (no dual isinstance breaks).
"""

from __future__ import annotations

import importlib
import sys
from types import ModuleType


def _unify_aliases(module: ModuleType, *names: str) -> ModuleType:
    """Register ``module`` under every name; return the shared object."""
    for name in names:
        existing = sys.modules.get(name)
        if existing is not None and existing is not module:
            # Prefer the already-registered object so late imports converge
            module = existing
            break
    for name in names:
        sys.modules[name] = module
    return module


def _install_shim(shim_name: str, relative_name: str) -> bool:
    """Install pure-Python shim if C extension missing.

    Returns True if the real C extension was already importable.
    """
    try:
        importlib.import_module(shim_name)
        return True
    except ImportError:
        pass

    aliases = (
        shim_name,
        f"codimension.parsers.{relative_name}",
        f"parsers.{relative_name}",
    )
    module = None
    for name in aliases[1:]:
        if name in sys.modules:
            module = sys.modules[name]
            break
    if module is None:
        module = importlib.import_module(f".{relative_name}", __name__)
    _unify_aliases(module, *aliases)
    return False


# Install cdmpyparser fallback if C extension not available
_CDMPYPARSER_AVAILABLE = _install_shim("cdmpyparser", "brief_ast")

# Install cdmcfparser fallback if C extension not available
_CDMCFPARSER_AVAILABLE = _install_shim("cdmcfparser", "flow_ast")
