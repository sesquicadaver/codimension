# -*- coding: utf-8 -*-
#
# codimension - graphics python two-way code editor and analyzer
# Copyright (C) 2020  Sergey Satskiy <sergey.satskiy@gmail.com>
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

"""Occurrences search result providers"""

import logging
import os.path
from collections import namedtuple

from autocomplete.completelists import getOccurrences
from utils.globals import GlobalData

from .resultprovideriface import SearchResultProviderIFace
from .searchsupport import ItemToSearchIn, getSearchItemIndex

# Lightweight stand-in matching the jedi-like fields ``build_occurrence_results`` reads.
_IndexOccurrence = namedtuple("_IndexOccurrence", "line module_path name")


def build_occurrence_results(definitions, fallback_file_name, symbol_name, uuid_resolver):
    """Collect occurrence matches grouped by file."""
    result = []
    for definition in definitions:
        if definition.line is None or definition.module_path is None:
            continue

        file_name = definition.module_path or fallback_file_name
        line_number = definition.line
        index = getSearchItemIndex(result, file_name)
        if index < 0:
            result.append(ItemToSearchIn(file_name, uuid_resolver(file_name)))
            index = len(result) - 1

        match_name = symbol_name or getattr(definition, "name", "")
        result[index].addMatch(match_name, line_number)
    return result


def definitions_from_symbol_index(index, symbol_name, *, include_references=True):
    """Adapt ``SymbolIndex`` query hits to jedi-like occurrence objects (R132).

    Does not change the default Jedi path in ``searchAgain``; callers may use
    this bridge when an index is available. Records without a ``line`` are
    skipped (same as invalid Jedi definitions).
    """
    if index is None or not symbol_name:
        return []
    records = list(index.find_definitions(symbol_name))
    if include_references:
        records.extend(index.find_references(symbol_name))
    out = []
    seen = set()
    for record in records:
        if record.line is None:
            continue
        key = (record.file, record.line, record.name)
        if key in seen:
            continue
        seen.add(key)
        out.append(_IndexOccurrence(record.line, record.file, record.name))
    return out


def build_occurrence_results_from_index(index, symbol_name, uuid_resolver, fallback_file_name=""):
    """Build search viewer items from a ``SymbolIndex`` without Jedi (R132)."""
    definitions = definitions_from_symbol_index(index, symbol_name)
    return build_occurrence_results(definitions, fallback_file_name, symbol_name, uuid_resolver)


class OccurrencesSearchProvider(SearchResultProviderIFace):
    """Occurrences search results provider"""

    def __init__(self):
        SearchResultProviderIFace.__init__(self)

    @staticmethod
    def serialize(parameters):
        """Provides a string which serializes the search parameters"""
        # parameters -> {'name': <string>,
        #                'filename': <string>,
        #                'line': <int>
        #                'column': <int>}
        return [
            ("Name", parameters["name"]),
            ("File name", parameters["filename"]),
            ("Line", str(parameters["line"])),
            ("Column", str(parameters["column"])),
        ]

    @staticmethod
    def _resolve_uuid(file_name):
        widget = GlobalData().mainWindow.getWidgetForFileName(file_name)
        if widget is None:
            return ""
        return widget.getUUID()

    @staticmethod
    def canRedo(parameters):
        """True when the saved occurrence search can be repeated from disk."""
        file_name = parameters.get("filename", "")
        return bool(file_name) and os.path.isabs(file_name) and os.path.isfile(file_name)

    @staticmethod
    def searchAgain(searchId, parameters, resultsViewer):
        """Repeats the occurrences search using the saved cursor position."""
        file_name = parameters["filename"]
        try:
            definitions = getOccurrences(
                None,
                file_name,
                parameters["line"],
                parameters["column"],
            )
            result = build_occurrence_results(
                definitions,
                file_name,
                parameters.get("name"),
                OccurrencesSearchProvider._resolve_uuid,
            )
            if not result:
                logging.warning("No occurrences found while repeating search for %s", file_name)
                return
            resultsViewer.showReport(
                OccurrencesSearchProvider.getName(),
                result,
                parameters,
                searchId,
            )
        except Exception as exc:
            logging.error(str(exc))

    @staticmethod
    def getName():
        """Provides the display name"""
        return "Occurrences"
