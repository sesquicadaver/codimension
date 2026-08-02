# -*- coding: utf-8 -*-
#
# codimension - GitHub credential resolver
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Resolve GitHub tokens: ``gh`` auth → OS keyring → file ``0600`` (T040/T041)."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from typing import Callable

from utils.settings import SETTINGS_DIR

KEYRING_SERVICE = "codimension-git"
KEYRING_USERNAME = "github-pat"
TOKEN_FILE = os.path.join(SETTINGS_DIR, "github_token")
TOKEN_FILE_MODE = 0o600


def _try_gh_token(gh_path: str = "gh") -> str | None:
    """Return token from ``gh auth token`` when authenticated."""
    exe = gh_path or "gh"
    if shutil.which(exe) is None and not os.path.isfile(exe):
        return None
    try:
        status = subprocess.run(
            [exe, "auth", "status"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if status.returncode != 0:
            return None
        proc = subprocess.run(
            [exe, "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode != 0:
            return None
        token = (proc.stdout or "").strip()
        return token or None
    except (OSError, subprocess.SubprocessError):
        return None


def _keyring_get() -> str | None:
    try:
        import keyring
    except ImportError:
        return None
    try:
        value = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
        return value.strip() if value else None
    except Exception as exc:  # keyring backends vary widely
        logging.debug("keyring get failed: %s", exc)
        return None


def _keyring_set(token: str) -> bool:
    try:
        import keyring
    except ImportError:
        return False
    try:
        keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, token)
        return True
    except Exception as exc:
        logging.debug("keyring set failed: %s", exc)
        return False


def _keyring_delete() -> None:
    try:
        import keyring
    except ImportError:
        return
    try:
        keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
    except Exception:
        pass


def _file_get() -> str | None:
    if not os.path.isfile(TOKEN_FILE):
        return None
    try:
        with open(TOKEN_FILE, encoding="utf-8") as handle:
            token = handle.read().strip()
        return token or None
    except OSError:
        return None


def _file_set(token: str) -> None:
    from utils.atomic_io import atomic_write_text

    atomic_write_text(TOKEN_FILE, token + "\n", mode=TOKEN_FILE_MODE)


def _file_delete() -> None:
    try:
        if os.path.isfile(TOKEN_FILE):
            os.unlink(TOKEN_FILE)
    except OSError:
        pass


def store_github_token(token: str) -> str:
    """Persist token preferring keyring; fall back to ``0600`` file. Returns backend name."""
    token = (token or "").strip()
    if not token:
        clear_stored_github_token()
        return "cleared"
    if _keyring_set(token):
        _file_delete()
        return "keyring"
    _file_set(token)
    return "file"


def clear_stored_github_token() -> None:
    """Remove token from keyring and file backends."""
    _keyring_delete()
    _file_delete()


def resolve_github_token(
    gh_path: str = "gh",
    *,
    gh_getter: Callable[[str], str | None] | None = None,
    keyring_getter: Callable[[], str | None] | None = None,
    file_getter: Callable[[], str | None] | None = None,
) -> tuple[str | None, str]:
    """Resolve token. Returns ``(token_or_None, source)``.

    ``source`` is one of: ``gh``, ``keyring``, ``file``, ``none``.
    """
    gh_fn = gh_getter or _try_gh_token
    key_fn = keyring_getter or _keyring_get
    file_fn = file_getter or _file_get

    token = gh_fn(gh_path)
    if token:
        return token, "gh"
    token = key_fn()
    if token:
        return token, "keyring"
    token = file_fn()
    if token:
        return token, "file"
    return None, "none"


def has_stored_github_token() -> bool:
    """True if keyring or file backend has a token (does not check ``gh``)."""
    return bool(_keyring_get() or _file_get())
