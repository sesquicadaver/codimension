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

"""Compatibility shim for pkg_resources (removed in setuptools 82+).

Provides get_distribution() and DistributionNotFound for plugins (cdmpylintplugin)
that still rely on pkg_resources.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, distribution


class DistributionNotFound(PackageNotFoundError):
    """Compatibility alias for pkg_resources.DistributionNotFound."""

    pass


def _get_location(dist) -> str | None:
    """Infer package location from distribution files."""
    if not dist.files:
        return None
    for f in dist.files:
        s = str(f)
        if "__init__.py" in s or (s.endswith(".py") and "/" in s):
            try:
                loc = f.locate().resolve().parent
                if "site-packages" in str(loc):
                    return str(loc)
            except (OSError, ValueError):
                continue
    return None


def get_distribution(name: str):
    """Return a distribution object with .version and .location (pkg_resources API)."""
    try:
        dist = distribution(name)
        loc = _get_location(dist)
        return _Distribution(dist.version, loc)

    except PackageNotFoundError:
        raise DistributionNotFound(f"No distribution found for {name}") from None


class _Distribution:
    """Minimal distribution object compatible with pkg_resources API."""

    __slots__ = ("version", "location")

    def __init__(self, version: str, location: str | None):
        self.version = version
        self.location = location or ""
