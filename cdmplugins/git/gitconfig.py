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

"""Git plugin configuration: paths to git/gh, default remote."""

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
from utils.settings import SETTINGS_DIR

CONFIG_FILE = SETTINGS_DIR + "git.plugin.conf"
CONFIG_SECTION = "general"
CONFIG_GIT_PATH = "git_path"
CONFIG_GH_PATH = "gh_path"
CONFIG_DEFAULT_REMOTE = "default_remote"
CONFIG_GITHUB_TOKEN = "github_token"

DEFAULT_GIT = "git"
DEFAULT_GH = "gh"
DEFAULT_REMOTE = "origin"


def load_config():
    """Load git plugin config. Returns dict with git_path, gh_path, default_remote, github_token."""
    result = {
        CONFIG_GIT_PATH: DEFAULT_GIT,
        CONFIG_GH_PATH: DEFAULT_GH,
        CONFIG_DEFAULT_REMOTE: DEFAULT_REMOTE,
        CONFIG_GITHUB_TOKEN: "",
    }
    if not os.path.exists(CONFIG_FILE):
        return result
    try:
        config = configparser.ConfigParser()
        config.read([CONFIG_FILE])
        if config.has_section(CONFIG_SECTION):
            result[CONFIG_GIT_PATH] = config.get(
                CONFIG_SECTION, CONFIG_GIT_PATH, fallback=DEFAULT_GIT
            ).strip() or DEFAULT_GIT
            result[CONFIG_GH_PATH] = config.get(
                CONFIG_SECTION, CONFIG_GH_PATH, fallback=DEFAULT_GH
            ).strip() or DEFAULT_GH
            result[CONFIG_DEFAULT_REMOTE] = config.get(
                CONFIG_SECTION, CONFIG_DEFAULT_REMOTE, fallback=DEFAULT_REMOTE
            ).strip() or DEFAULT_REMOTE
            result[CONFIG_GITHUB_TOKEN] = config.get(
                CONFIG_SECTION, CONFIG_GITHUB_TOKEN, fallback=""
            ).strip()
    except (configparser.Error, OSError):
        pass
    return result


def save_config(git_path, gh_path, default_remote, github_token=""):
    """Save git plugin config."""
    config = configparser.ConfigParser()
    config[CONFIG_SECTION] = {
        CONFIG_GIT_PATH: (git_path or "").strip() or DEFAULT_GIT,
        CONFIG_GH_PATH: (gh_path or "").strip() or DEFAULT_GH,
        CONFIG_DEFAULT_REMOTE: (default_remote or "").strip() or DEFAULT_REMOTE,
        CONFIG_GITHUB_TOKEN: (github_token or "").strip(),
    }
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            config.write(f)
    except OSError:
        pass


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
    """Return configured GitHub Personal Access Token (PAT)."""
    return load_config()[CONFIG_GITHUB_TOKEN]


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

        self.__tokenEdit = QLineEdit(self)
        self.__tokenEdit.setPlaceholderText("ghp_xxx or fine-grained token")
        self.__tokenEdit.setEchoMode(QLineEdit.Password)
        self.__tokenEdit.setText(cfg.get(CONFIG_GITHUB_TOKEN, ""))
        grid.addWidget(QLabel("GitHub token (PAT):", self), 3, 0)
        grid.addWidget(self.__tokenEdit, 3, 1)

        layout.addLayout(grid)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_values(self):
        """Return (git_path, gh_path, default_remote, github_token)."""
        return (
            self.__gitEdit.text().strip() or DEFAULT_GIT,
            self.__ghEdit.text().strip() or DEFAULT_GH,
            self.__remoteEdit.text().strip() or DEFAULT_REMOTE,
            self.__tokenEdit.text().strip(),
        )
