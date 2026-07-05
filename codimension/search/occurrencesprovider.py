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

from autocomplete.completelists import getOccurrences
from utils.globals import GlobalData

from .resultprovideriface import SearchResultProviderIFace
from .searchsupport import ItemToSearchIn, getSearchItemIndex


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
