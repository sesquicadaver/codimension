# -*- coding: utf-8 -*-
#
# codimension - slow project scan ignore dialog
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Dialog: optionally exclude the directory that is delaying a slow project scan."""

from __future__ import annotations

from .qt import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


class SlowScanIgnoreDialog(QDialog):
    """Offer optional excludes for the hot directory delaying the project scan.

    Checkboxes start unchecked (no recommendation applied yet). **Accept** is
    enabled only after at least one checkbox is checked and applies those
    excludes then rescans. **Continue** always dismisses without applying
    changes (scan keeps going).
    """

    def __init__(self, relative_dir: str, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowTitle("Slow project scan")
        self.setModal(True)
        self.resize(520, 220)
        self.__relative_dir = relative_dir

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Project scan is taking longer than 30 seconds.\nMost time is currently spent reading this directory:",
                self,
            )
        )
        path_label = QLabel(relative_dir, self)
        path_label.setWordWrap(True)
        layout.addWidget(path_label)

        checks = QHBoxLayout()
        self.analysisCheck = QCheckBox("Exclude from analysis", self)
        self.analysisCheck.setChecked(False)
        self.analysisCheck.setToolTip("Exclude from analysis / filesList / watcher")
        self.treeCheck = QCheckBox("Hide from project tree", self)
        self.treeCheck.setChecked(False)
        self.treeCheck.setToolTip("Hide from Project tree UI")
        checks.addWidget(self.analysisCheck)
        checks.addWidget(self.treeCheck)
        checks.addStretch(1)
        layout.addLayout(checks)

        layout.addWidget(
            QLabel(
                "Accept applies the selected options and rescans. "
                "Continue leaves excludes unchanged and keeps scanning. "
                "You can edit excludes later in Project Properties.",
                self,
            )
        )

        buttons = QDialogButtonBox(self)
        accept_btn = buttons.addButton("Accept", QDialogButtonBox.AcceptRole)
        continue_btn = buttons.addButton("Continue", QDialogButtonBox.RejectRole)
        assert isinstance(accept_btn, QPushButton)
        assert isinstance(continue_btn, QPushButton)
        self.__acceptButton: QPushButton = accept_btn
        self.__continueButton: QPushButton = continue_btn
        self.__acceptButton.setEnabled(False)
        self.__acceptButton.clicked.connect(self.accept)
        self.__continueButton.clicked.connect(self.reject)
        layout.addWidget(buttons)

        self.analysisCheck.toggled.connect(self.__onCheckboxToggled)
        self.treeCheck.toggled.connect(self.__onCheckboxToggled)

    def __onCheckboxToggled(self, _checked: bool = False) -> None:
        """Enable Accept only when at least one exclude option is selected."""
        self.__acceptButton.setEnabled(self.analysisCheck.isChecked() or self.treeCheck.isChecked())

    def isAcceptEnabled(self) -> bool:
        """True when Accept can apply at least one selected exclude option."""
        return self.__acceptButton.isEnabled()

    def selectedExcludes(self) -> tuple[list[str], list[str]]:
        """Return ``(excludeFromAnalysis, excludeFromProjectTree)`` for this directory."""
        analysis: list[str] = []
        tree: list[str] = []
        if self.analysisCheck.isChecked():
            analysis.append(self.__relative_dir)
        if self.treeCheck.isChecked():
            tree.append(self.__relative_dir)
        return analysis, tree
