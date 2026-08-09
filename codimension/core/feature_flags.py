# -*- coding: utf-8 -*-
#
# codimension - persistent experimental feature flags (R174)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Persistent feature flags for experimental plugins/UI (R174).

Flags default to off. Optional environment overrides win when the env key is
present and non-empty. Storage is a small JSON file under the user config dir
(``~/.codimension3/feature_flags.json``). Qt-free.
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Mapping, MutableMapping, Optional

#: Flag id for experimental AI explain/suggest UI (R152).
FLAG_AI_UI = "ai_ui"

#: Known flag identifiers (unknown keys are ignored on load / rejected on set).
KNOWN_FLAGS: frozenset[str] = frozenset({FLAG_AI_UI})

#: Optional env override per flag (non-empty value wins over the store).
FLAG_ENV_OVERRIDES: Mapping[str, str] = {
    FLAG_AI_UI: "CDM_AI_UI",
}

_TRUTHY = frozenset({"1", "true", "yes", "on"})
_CONFIG_DIR = ".codimension3"
_FLAGS_FILENAME = "feature_flags.json"

_default_store: Optional["FeatureFlagsStore"] = None


def default_feature_flags_path(home: Optional[str] = None) -> str:
    """Return the default on-disk path for the flags JSON file."""
    base = os.path.expanduser(home if home is not None else "~")
    return os.path.join(base, _CONFIG_DIR, _FLAGS_FILENAME)


def parse_truthy(value: object) -> bool:
    """Interpret common truthy strings; everything else is False."""
    return str(value).strip().lower() in _TRUTHY


def _atomic_write_json(path: str, payload: Mapping[str, bool]) -> None:
    """Write JSON atomically (temp file in the same directory + replace)."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, mode=0o755, exist_ok=True)
    text = json.dumps({"flags": dict(payload)}, indent=2, sort_keys=True) + "\n"
    fd, tmp_path = tempfile.mkstemp(prefix=".cdm-flags-", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            if os.path.isfile(tmp_path):
                os.unlink(tmp_path)
        except OSError:
            pass
        raise


class FeatureFlagsStore:
    """In-memory flag map with optional JSON persistence."""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path
        self._flags: dict[str, bool] = {name: False for name in sorted(KNOWN_FLAGS)}
        if path is not None and os.path.isfile(path):
            self.load()

    def load(self) -> None:
        """Reload flags from ``path`` when set; missing/invalid file → defaults."""
        self._flags = {name: False for name in sorted(KNOWN_FLAGS)}
        if not self.path or not os.path.isfile(self.path):
            return
        try:
            with open(self.path, encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError):
            return
        section = raw.get("flags") if isinstance(raw, dict) else None
        if not isinstance(section, dict):
            return
        for name, value in section.items():
            key = str(name)
            if key in KNOWN_FLAGS:
                self._flags[key] = bool(value)

    def save(self) -> None:
        """Persist current flags to ``path`` (no-op when path is None)."""
        if self.path is None:
            return
        _atomic_write_json(self.path, self._flags)

    def is_enabled(self, flag: str) -> bool:
        """Return the stored value for a known flag (unknown → False)."""
        return bool(self._flags.get(flag, False))

    def set_enabled(self, flag: str, enabled: bool, *, persist: bool = True) -> None:
        """Set a known flag; raises ``ValueError`` for unknown ids."""
        if flag not in KNOWN_FLAGS:
            raise ValueError(f"unknown feature flag: {flag!r}")
        self._flags[flag] = bool(enabled)
        if persist:
            self.save()

    def as_dict(self) -> dict[str, bool]:
        """Return a copy of all known flags."""
        return dict(self._flags)


def get_feature_flags_store() -> FeatureFlagsStore:
    """Process-wide default store (lazy; path under the user config dir)."""
    global _default_store
    if _default_store is None:
        _default_store = FeatureFlagsStore(default_feature_flags_path())
    return _default_store


def reset_feature_flags_store_for_tests() -> None:
    """Drop the process-wide store (tests only)."""
    global _default_store
    _default_store = None


def is_feature_enabled(
    flag: str,
    *,
    store: Optional[FeatureFlagsStore] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> bool:
    """Resolve a flag: non-empty env override, else persistent store.

    When ``environ`` is passed explicitly and the override key is absent,
    the disk store is not consulted (keeps unit tests isolated) unless
    ``store`` is provided.
    """
    env_key = FLAG_ENV_OVERRIDES.get(flag)
    if env_key is not None:
        env: Mapping[str, str] = os.environ if environ is None else environ
        if env_key in env and str(env.get(env_key, "")).strip() != "":
            return parse_truthy(env[env_key])

    if store is not None:
        return store.is_enabled(flag)
    if environ is not None:
        return False
    return get_feature_flags_store().is_enabled(flag)


def set_feature_enabled(
    flag: str,
    enabled: bool,
    *,
    store: Optional[FeatureFlagsStore] = None,
    persist: bool = True,
) -> None:
    """Set a flag on the given or process-wide store."""
    active = store if store is not None else get_feature_flags_store()
    active.set_enabled(flag, enabled, persist=persist)


def enable_flag_in_environ(flag: str, environ: MutableMapping[str, str]) -> None:
    """Set the env override for ``flag`` in a mutable mapping (tests/helpers)."""
    env_key = FLAG_ENV_OVERRIDES.get(flag)
    if env_key is None:
        raise ValueError(f"flag has no env override: {flag!r}")
    environ[env_key] = "1"


__all__ = [
    "FLAG_AI_UI",
    "FLAG_ENV_OVERRIDES",
    "KNOWN_FLAGS",
    "FeatureFlagsStore",
    "default_feature_flags_path",
    "enable_flag_in_environ",
    "get_feature_flags_store",
    "is_feature_enabled",
    "parse_truthy",
    "reset_feature_flags_store_for_tests",
    "set_feature_enabled",
]
