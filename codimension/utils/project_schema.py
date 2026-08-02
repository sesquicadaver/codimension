# -*- coding: utf-8 -*-
#
# codimension - `.cdm3` project schema validation
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Validate Codimension project JSON props (T043)."""

from __future__ import annotations

from typing import Any

# Expected types for known keys (missing keys are filled from defaults elsewhere).
_KEY_TYPES: dict[str, type | tuple[type, ...]] = {
    "scriptname": str,
    "mddocfile": str,
    "creationdate": str,
    "author": str,
    "license": str,
    "copyright": str,
    "version": str,
    "email": str,
    "description": str,
    "uuid": str,
    "importdirs": list,
    "excludeFromAnalysis": list,
    "encoding": str,
    "pythoninterpreter": str,
}


class ProjectSchemaError(ValueError):
    """Raised when a `.cdm3` document fails schema checks."""


def validate_project_props(props: Any) -> dict[str, Any]:
    """Return ``props`` if valid; raise :class:`ProjectSchemaError` otherwise."""
    if not isinstance(props, dict):
        raise ProjectSchemaError("project file root must be a JSON object")
    for key, expected in _KEY_TYPES.items():
        if key not in props:
            continue
        value = props[key]
        if not isinstance(value, expected):
            raise ProjectSchemaError(f"project field '{key}' has invalid type {type(value).__name__}")
        if isinstance(value, list):
            for idx, item in enumerate(value):
                if not isinstance(item, str):
                    raise ProjectSchemaError(f"project field '{key}[{idx}]' must be a string")
    return props
