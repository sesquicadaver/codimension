# -*- coding: utf-8 -*-
#
# codimension - graphics python two-way code editor and analyzer
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Watchpoint related utilities"""

_CREATED_FLAG = "??created??"
_CHANGED_FLAG = "??changed??"
_WATCH_FLAGS = (_CREATED_FLAG, _CHANGED_FLAG)


def formatRemoteWatchCondition(condition, special):
    """Builds the condition string sent to the debuggee."""
    if special in _WATCH_FLAGS:
        return f"{condition} {special}"
    return condition


def parseRemoteWatchCondition(remote_condition):
    """Splits a debuggee watch condition into expression and flag."""
    for flag in _WATCH_FLAGS:
        suffix = f" {flag}"
        if remote_condition.endswith(suffix):
            return remote_condition[: -len(suffix)], flag
    return remote_condition, ""
