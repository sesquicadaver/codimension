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

"""Dialog to edit a single watch expression"""

from ui.combobox import CDMComboBox
from ui.qt import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QSpinBox,
    Qt,
    QVBoxLayout,
)
from utils.pixmapcache import getIcon


class WatchpointEditDialog(QDialog):
    """Dialog to add or edit a debugger watch expression."""

    def __init__(self, data, parent=None):
        """
        data: (condition, temporary, enabled, ignore_count, special)
        """
        QDialog.__init__(self, parent)

        self.__origData = data
        self.setWindowTitle("Edit watch expression")
        self.setWindowIcon(getIcon("bpprops.png"))
        self.__createLayout(data)
        self.__OKButton.setEnabled(data[0] == "")

        self.__conditionValue.lineEdit().textChanged.connect(self.__changed)
        self.__specialValue.currentIndexChanged.connect(self.__changed)
        self.__ignoreValue.valueChanged.connect(self.__changed)
        self.__enabled.stateChanged.connect(self.__changed)
        self.__tempCheckbox.stateChanged.connect(self.__changed)

    def __createLayout(self, data):
        """Creates the dialog layout"""
        condition, temporary, enabled, ignore_count, special = data

        self.resize(420, 170)
        self.setSizeGripEnabled(True)

        layout = QVBoxLayout(self)
        gridLayout = QGridLayout()

        conditionLabel = QLabel("Condition:")
        gridLayout.addWidget(conditionLabel, 0, 0)
        self.__conditionValue = CDMComboBox(True)
        self.__conditionValue.lineEdit().setText(condition)
        gridLayout.addWidget(self.__conditionValue, 0, 1)

        specialLabel = QLabel("Trigger:")
        gridLayout.addWidget(specialLabel, 1, 0)
        self.__specialValue = QComboBox()
        self.__specialValue.addItem("Value is true", "")
        self.__specialValue.addItem("Object created", "??created??")
        self.__specialValue.addItem("Value changed", "??changed??")
        specialIndex = max(0, self.__specialValue.findData(special))
        self.__specialValue.setCurrentIndex(specialIndex)
        gridLayout.addWidget(self.__specialValue, 1, 1)

        ignoreLabel = QLabel("Ignore count:")
        gridLayout.addWidget(ignoreLabel, 2, 0)
        self.__ignoreValue = QSpinBox()
        self.__ignoreValue.setMinimum(0)
        self.__ignoreValue.setValue(ignore_count)
        gridLayout.addWidget(self.__ignoreValue, 2, 1)
        layout.addLayout(gridLayout)

        self.__tempCheckbox = QCheckBox("&Temporary")
        self.__tempCheckbox.setChecked(temporary)
        layout.addWidget(self.__tempCheckbox)
        self.__enabled = QCheckBox("&Enabled")
        self.__enabled.setChecked(enabled)
        layout.addWidget(self.__enabled)

        buttonBox = QDialogButtonBox(self)
        buttonBox.setOrientation(Qt.Horizontal)
        buttonBox.setStandardButtons(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.__OKButton = buttonBox.button(QDialogButtonBox.Ok)
        self.__OKButton.setDefault(True)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.close)
        layout.addWidget(buttonBox)

        self.__conditionValue.setFocus()

    def __changed(self, skipped=None):
        """Triggered when something has been changed"""
        hasCondition = bool(self.__conditionValue.lineEdit().text().strip())
        self.__OKButton.setEnabled(hasCondition)

    def getData(self):
        """Provides watch expression fields as a tuple."""
        return (
            self.__conditionValue.lineEdit().text().strip(),
            self.__tempCheckbox.isChecked(),
            self.__enabled.isChecked(),
            self.__ignoreValue.value(),
            self.__specialValue.currentData(),
        )
