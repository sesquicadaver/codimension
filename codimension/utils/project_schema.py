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

import os
import uuid
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


def canonicalize_project_uuid(value: str) -> str:
    """Return canonical UUID string or raise :class:`ProjectSchemaError`.

    Rejects path separators and non-UUID strings (audit P0 path traversal via
    ``uuid`` in ``.cdm3``).
    """
    if not isinstance(value, str):
        raise ProjectSchemaError(f"project field 'uuid' has invalid type {type(value).__name__}")
    stripped = value.strip()
    if not stripped:
        raise ProjectSchemaError("project field 'uuid' must not be empty")
    if os.sep in stripped or (os.altsep and os.altsep in stripped) or ".." in stripped:
        raise ProjectSchemaError("project field 'uuid' must not contain path components")
    try:
        return str(uuid.UUID(stripped))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ProjectSchemaError(f"project field 'uuid' must be a valid UUID: {exc}") from exc


def safe_user_project_dir(settings_dir: str, project_uuid: str) -> str:
    """Return ``settings_dir/<canonical-uuid>/`` contained under ``settings_dir``.

    Raises :class:`ProjectSchemaError` on invalid UUID or path traversal.
    """
    safe_name = canonicalize_project_uuid(project_uuid)
    settings_root = os.path.realpath(settings_dir)
    candidate = os.path.realpath(os.path.join(settings_root, safe_name))
    try:
        common = os.path.commonpath([candidate, settings_root])
    except ValueError as exc:
        # Different drives on Windows, etc.
        raise ProjectSchemaError("project uuid resolves outside settings directory") from exc
    if common != settings_root:
        raise ProjectSchemaError("project uuid resolves outside settings directory")
    return candidate + os.sep


def validate_project_props(props: Any) -> dict[str, Any]:
    """Return ``props`` if valid; raise :class:`ProjectSchemaError` otherwise.

    When ``uuid`` is present and non-empty, it is canonicalized in-place to the
    standard UUID string form.
    """
    if not isinstance(props, dict):
        raise ProjectSchemaError("project file root must be a JSON object")
    for key, expected in _KEY_TYPES.items():
        if key not in props:
            continue
        value = props[key]
        if key == "uuid":
            if not isinstance(value, str):
                raise ProjectSchemaError(f"project field 'uuid' has invalid type {type(value).__name__}")
            if value.strip() == "":
                # Empty uuid is allowed at load; project.py regenerates it.
                props[key] = ""
                continue
            props[key] = canonicalize_project_uuid(value)
            continue
        if not isinstance(value, expected):
            raise ProjectSchemaError(f"project field '{key}' has invalid type {type(value).__name__}")
        if isinstance(value, list):
            for idx, item in enumerate(value):
                if not isinstance(item, str):
                    raise ProjectSchemaError(f"project field '{key}[{idx}]' must be a string")
    return props
