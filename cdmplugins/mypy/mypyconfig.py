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

"""Mypy plugin configuration: extra command-line arguments."""

import configparser
import os.path
import shlex

from ui.qt import QDialog, QDialogButtonBox, QGridLayout, QLabel, QLineEdit, QVBoxLayout
from utils.settings import SETTINGS_DIR

CONFIG_FILE = SETTINGS_DIR + "mypy.plugin.conf"
CONFIG_SECTION = "general"
CONFIG_EXTRA_ARGS = "extra_args"


def load_extra_args():
    """Load extra args. Returns list of str (empty if none)."""
    if not os.path.exists(CONFIG_FILE):
        return []
    try:
        config = configparser.ConfigParser()
        config.read([CONFIG_FILE])
        raw = config.get(CONFIG_SECTION, CONFIG_EXTRA_ARGS, fallback="").strip()
        return shlex.split(raw) if raw else []
    except (configparser.Error, OSError, ValueError):
        return []


def save_extra_args(value):
    """Save extra args. value: str (space-separated)."""
    config = configparser.ConfigParser()
    config[CONFIG_SECTION] = {CONFIG_EXTRA_ARGS: (value or "").strip()}
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            config.write(f)
    except OSError:
        pass


class MypyConfigDialog(QDialog):
    """Configuration dialog for Mypy plugin."""

    def __init__(self, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowTitle("Mypy — Configuration")

        raw = " ".join(load_extra_args())
        layout = QVBoxLayout(self)
        grid = QGridLayout()
        self.__extraEdit = QLineEdit(self)
        self.__extraEdit.setPlaceholderText("e.g. --strict --no-incremental")
        self.__extraEdit.setText(raw)
        grid.addWidget(QLabel("Extra arguments:", self), 0, 0)
        grid.addWidget(self.__extraEdit, 0, 1)
        layout.addLayout(grid)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_extra_args(self):
        """Return extra args as string."""
        return self.__extraEdit.text().strip()
