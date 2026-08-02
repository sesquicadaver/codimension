# -*- coding: utf-8 -*-
#
# Codimension - Python 3 experimental IDE
# Copyright (C) 2025  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Git plugin configuration: paths to git/gh, default remote, secure PAT storage."""

import configparser
import os.path

from ui.qt import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)
from utils.atomic_io import atomic_write_via
from utils.settings import SETTINGS_DIR

from .credentials import has_stored_github_token, resolve_github_token, store_github_token

CONFIG_FILE = SETTINGS_DIR + "git.plugin.conf"
CONFIG_SECTION = "general"
CONFIG_GIT_PATH = "git_path"
CONFIG_GH_PATH = "gh_path"
CONFIG_DEFAULT_REMOTE = "default_remote"
CONFIG_GITHUB_TOKEN = "github_token"  # legacy plaintext key — scrubbed on load/save
CONFIG_GITHUB_USERNAME = "github_username"
CONFIG_GITHUB_REPO_OVERRIDE = "github_repo_override"

DEFAULT_GIT = "git"
DEFAULT_GH = "gh"
DEFAULT_REMOTE = "origin"


def _write_config_dict(section_dict: dict) -> None:
    """Atomically write git.plugin.conf without secrets."""
    config = configparser.ConfigParser()
    config[CONFIG_SECTION] = section_dict

    def _writer(tmp_path: str) -> None:
        with open(tmp_path, "w", encoding="utf-8") as handle:
            config.write(handle)

    atomic_write_via(CONFIG_FILE, _writer, mode=0o600)


def _scrub_plaintext_token(config: configparser.ConfigParser) -> str | None:
    """Migrate legacy plaintext token out of conf; return token if found."""
    if not config.has_section(CONFIG_SECTION):
        return None
    if not config.has_option(CONFIG_SECTION, CONFIG_GITHUB_TOKEN):
        return None
    token = config.get(CONFIG_SECTION, CONFIG_GITHUB_TOKEN, fallback="").strip()
    config.remove_option(CONFIG_SECTION, CONFIG_GITHUB_TOKEN)
    return token or None


def load_config():
    """Load git plugin config (never returns a live token in the dict).

    Returns dict with git_path, gh_path, default_remote, github_username,
    github_repo_override, and ``github_token_configured`` bool.
    """
    result = {
        CONFIG_GIT_PATH: DEFAULT_GIT,
        CONFIG_GH_PATH: DEFAULT_GH,
        CONFIG_DEFAULT_REMOTE: DEFAULT_REMOTE,
        CONFIG_GITHUB_USERNAME: "",
        CONFIG_GITHUB_REPO_OVERRIDE: "",
        "github_token_configured": False,
    }
    if not os.path.exists(CONFIG_FILE):
        result["github_token_configured"] = has_stored_github_token()
        return result
    try:
        config = configparser.ConfigParser()
        config.read([CONFIG_FILE])
        migrated = _scrub_plaintext_token(config)
        if config.has_section(CONFIG_SECTION):
            result[CONFIG_GIT_PATH] = (
                config.get(CONFIG_SECTION, CONFIG_GIT_PATH, fallback=DEFAULT_GIT).strip() or DEFAULT_GIT
            )
            result[CONFIG_GH_PATH] = (
                config.get(CONFIG_SECTION, CONFIG_GH_PATH, fallback=DEFAULT_GH).strip() or DEFAULT_GH
            )
            result[CONFIG_DEFAULT_REMOTE] = (
                config.get(CONFIG_SECTION, CONFIG_DEFAULT_REMOTE, fallback=DEFAULT_REMOTE).strip() or DEFAULT_REMOTE
            )
            result[CONFIG_GITHUB_USERNAME] = config.get(CONFIG_SECTION, CONFIG_GITHUB_USERNAME, fallback="").strip()
            result[CONFIG_GITHUB_REPO_OVERRIDE] = config.get(
                CONFIG_SECTION, CONFIG_GITHUB_REPO_OVERRIDE, fallback=""
            ).strip()
        if migrated:
            store_github_token(migrated)
            # Persist scrubbed conf without plaintext token
            _write_config_dict(
                {
                    CONFIG_GIT_PATH: result[CONFIG_GIT_PATH],
                    CONFIG_GH_PATH: result[CONFIG_GH_PATH],
                    CONFIG_DEFAULT_REMOTE: result[CONFIG_DEFAULT_REMOTE],
                    CONFIG_GITHUB_USERNAME: result[CONFIG_GITHUB_USERNAME],
                    CONFIG_GITHUB_REPO_OVERRIDE: result[CONFIG_GITHUB_REPO_OVERRIDE],
                }
            )
        result["github_token_configured"] = has_stored_github_token()
    except (configparser.Error, OSError):
        result["github_token_configured"] = has_stored_github_token()
    return result


def save_config(
    git_path,
    gh_path,
    default_remote,
    github_username="",
    github_token="",
):
    """Save git plugin config; store PAT via secure backends, never in conf."""
    cfg = load_config()
    token = (github_token or "").strip()
    if token:
        store_github_token(token)
    # Empty token field means "keep existing" — use clear via explicit API only
    _write_config_dict(
        {
            CONFIG_GIT_PATH: (git_path or "").strip() or DEFAULT_GIT,
            CONFIG_GH_PATH: (gh_path or "").strip() or DEFAULT_GH,
            CONFIG_DEFAULT_REMOTE: (default_remote or "").strip() or DEFAULT_REMOTE,
            CONFIG_GITHUB_USERNAME: (github_username or "").strip(),
            CONFIG_GITHUB_REPO_OVERRIDE: cfg.get(CONFIG_GITHUB_REPO_OVERRIDE, ""),
        }
    )


def get_git_path():
    """Return configured path to git executable."""
    return load_config()[CONFIG_GIT_PATH]


def get_gh_path():
    """Return configured path to gh executable."""
    return load_config()[CONFIG_GH_PATH]


def get_default_remote():
    """Return configured default remote name."""
    return load_config()[CONFIG_DEFAULT_REMOTE]


def get_github_token():
    """Resolve GitHub PAT: gh auth → keyring → file 0600."""
    cfg = load_config()
    # Migrate any leftover plaintext first (load_config already scrubs)
    token, _source = resolve_github_token(cfg.get(CONFIG_GH_PATH, DEFAULT_GH))
    return token or ""


def get_github_username():
    """Return configured GitHub username (for Git credential / HTTPS push)."""
    return load_config()[CONFIG_GITHUB_USERNAME]


def get_github_repo_override():
    """Return manual repo override: owner/repo or full URL. Empty = use git remote."""
    return load_config()[CONFIG_GITHUB_REPO_OVERRIDE]


def save_repo_override(repo_override: str):
    """Save only the repository override field."""
    cfg = load_config()
    _write_config_dict(
        {
            CONFIG_GIT_PATH: cfg[CONFIG_GIT_PATH],
            CONFIG_GH_PATH: cfg[CONFIG_GH_PATH],
            CONFIG_DEFAULT_REMOTE: cfg[CONFIG_DEFAULT_REMOTE],
            CONFIG_GITHUB_USERNAME: cfg[CONFIG_GITHUB_USERNAME],
            CONFIG_GITHUB_REPO_OVERRIDE: (repo_override or "").strip(),
        }
    )


class GitConfigDialog(QDialog):
    """Configuration dialog for Git plugin."""

    def __init__(self, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowTitle("Git — Configuration")

        cfg = load_config()
        layout = QVBoxLayout(self)
        grid = QGridLayout()

        self.__gitEdit = QLineEdit(self)
        self.__gitEdit.setPlaceholderText(DEFAULT_GIT)
        self.__gitEdit.setText(cfg[CONFIG_GIT_PATH])
        grid.addWidget(QLabel("Path to git:", self), 0, 0)
        grid.addWidget(self.__gitEdit, 0, 1)

        self.__ghEdit = QLineEdit(self)
        self.__ghEdit.setPlaceholderText(DEFAULT_GH)
        self.__ghEdit.setText(cfg[CONFIG_GH_PATH])
        grid.addWidget(QLabel("Path to gh (GitHub CLI):", self), 1, 0)
        grid.addWidget(self.__ghEdit, 1, 1)

        self.__remoteEdit = QLineEdit(self)
        self.__remoteEdit.setPlaceholderText(DEFAULT_REMOTE)
        self.__remoteEdit.setText(cfg[CONFIG_DEFAULT_REMOTE])
        grid.addWidget(QLabel("Default remote:", self), 2, 0)
        grid.addWidget(self.__remoteEdit, 2, 1)

        self.__usernameEdit = QLineEdit(self)
        self.__usernameEdit.setPlaceholderText("GitHub username")
        self.__usernameEdit.setText(cfg.get(CONFIG_GITHUB_USERNAME, ""))
        grid.addWidget(QLabel("GitHub username:", self), 3, 0)
        grid.addWidget(self.__usernameEdit, 3, 1)

        self.__tokenEdit = QLineEdit(self)
        if cfg.get("github_token_configured"):
            self.__tokenEdit.setPlaceholderText("•••• saved (enter new token to replace)")
        else:
            self.__tokenEdit.setPlaceholderText("ghp_xxx or fine-grained token (or use gh auth)")
        self.__tokenEdit.setEchoMode(QLineEdit.Password)
        # Never prefill stored token into the UI
        self.__tokenEdit.setText("")
        grid.addWidget(QLabel("GitHub token (PAT):", self), 4, 0)
        grid.addWidget(self.__tokenEdit, 4, 1)

        layout.addLayout(grid)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_values(self):
        """Return (git_path, gh_path, default_remote, github_username, github_token)."""
        return (
            self.__gitEdit.text().strip() or DEFAULT_GIT,
            self.__ghEdit.text().strip() or DEFAULT_GH,
            self.__remoteEdit.text().strip() or DEFAULT_REMOTE,
            self.__usernameEdit.text().strip(),
            self.__tokenEdit.text().strip(),
        )
