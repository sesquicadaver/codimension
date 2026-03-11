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
"""

# Install cdmpyparser fallback if C extension not available
try:
    import cdmpyparser  # noqa: F401
    _CDMPYPARSER_AVAILABLE = True
except ImportError:
    _CDMPYPARSER_AVAILABLE = False
    import sys as _sys

    from . import brief_ast as _brief_fallback
    _sys.modules['cdmpyparser'] = _brief_fallback

# Install cdmcfparser fallback if C extension not available
try:
    import cdmcfparser  # noqa: F401
    _CDMCFPARSER_AVAILABLE = True
except ImportError:
    _CDMCFPARSER_AVAILABLE = False
    import sys as _sys

    from . import flow_ast as _flow_fallback
    _sys.modules['cdmcfparser'] = _flow_fallback
