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

from ui.qt import QDialog, QDialogButtonBox, QFormLayout, QLineEdit
from utils.settings import SETTINGS_DIR

CONFIG_FILE = SETTINGS_DIR + "git.plugin.conf"
CONFIG_SECTION = "general"
CONFIG_GIT_PATH = "git_path"
CONFIG_GH_PATH = "gh_path"
CONFIG_DEFAULT_REMOTE = "default_remote"

DEFAULT_GIT = "git"
DEFAULT_GH = "gh"
DEFAULT_REMOTE = "origin"


def load_config():
    """Load git plugin config. Returns dict with git_path, gh_path, default_remote."""
    result = {
        CONFIG_GIT_PATH: DEFAULT_GIT,
        CONFIG_GH_PATH: DEFAULT_GH,
        CONFIG_DEFAULT_REMOTE: DEFAULT_REMOTE,
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
    except (configparser.Error, OSError):
        pass
    return result


def save_config(git_path, gh_path, default_remote):
    """Save git plugin config."""
    config = configparser.ConfigParser()
    config[CONFIG_SECTION] = {
        CONFIG_GIT_PATH: (git_path or "").strip() or DEFAULT_GIT,
        CONFIG_GH_PATH: (gh_path or "").strip() or DEFAULT_GH,
        CONFIG_DEFAULT_REMOTE: (default_remote or "").strip() or DEFAULT_REMOTE,
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


class GitConfigDialog(QDialog):
    """Configuration dialog for Git plugin."""

    def __init__(self, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowTitle("Git — Configuration")

        cfg = load_config()
        layout = QFormLayout(self)

        self.__gitEdit = QLineEdit(self)
        self.__gitEdit.setPlaceholderText(DEFAULT_GIT)
        self.__gitEdit.setText(cfg[CONFIG_GIT_PATH])
        layout.addRow("Path to git:", self.__gitEdit)

        self.__ghEdit = QLineEdit(self)
        self.__ghEdit.setPlaceholderText(DEFAULT_GH)
        self.__ghEdit.setText(cfg[CONFIG_GH_PATH])
        layout.addRow("Path to gh (GitHub CLI):", self.__ghEdit)

        self.__remoteEdit = QLineEdit(self)
        self.__remoteEdit.setPlaceholderText(DEFAULT_REMOTE)
        self.__remoteEdit.setText(cfg[CONFIG_DEFAULT_REMOTE])
        layout.addRow("Default remote:", self.__remoteEdit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_values(self):
        """Return (git_path, gh_path, default_remote)."""
        return (
            self.__gitEdit.text().strip() or DEFAULT_GIT,
            self.__ghEdit.text().strip() or DEFAULT_GH,
            self.__remoteEdit.text().strip() or DEFAULT_REMOTE,
        )
