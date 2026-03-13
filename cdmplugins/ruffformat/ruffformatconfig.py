# -*- coding: utf-8 -*-
#
# codimension - graphics python two-way code editor and analyzer
# Copyright (C) 2025  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Ruff format plugin configuration dialog."""

import configparser
import os.path

from ui.qt import QCheckBox, QDialog, QDialogButtonBox, QVBoxLayout
from utils.settings import SETTINGS_DIR

CONFIG_FILE = SETTINGS_DIR + "ruffformat.plugin.conf"
CONFIG_SECTION = "general"
CONFIG_FORMAT_ON_SAVE = "format_on_save"


def loadFormatOnSave():
    """Load format-on-save setting. Default False."""
    if not os.path.exists(CONFIG_FILE):
        return False
    try:
        config = configparser.ConfigParser()
        config.read([CONFIG_FILE])
        return config.getboolean(CONFIG_SECTION, CONFIG_FORMAT_ON_SAVE, fallback=False)
    except Exception:
        return False


def saveFormatOnSave(value):
    """Save format-on-save setting."""
    config = configparser.ConfigParser()
    config[CONFIG_SECTION] = {CONFIG_FORMAT_ON_SAVE: str(value)}
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            config.write(f)
    except OSError:
        pass


class RuffFormatConfigDialog(QDialog):
    """Configuration dialog for ruff format plugin."""

    def __init__(self, formatOnSave, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowTitle("Ruff format — Configuration")
        self.__formatOnSave = formatOnSave

        layout = QVBoxLayout(self)
        self.__formatOnSaveCb = QCheckBox("Format on save (Python files only)", self)
        self.__formatOnSaveCb.setChecked(formatOnSave)
        layout.addWidget(self.__formatOnSaveCb)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def getFormatOnSave(self):
        """Returns the format-on-save checkbox state."""
        return self.__formatOnSaveCb.isChecked()
