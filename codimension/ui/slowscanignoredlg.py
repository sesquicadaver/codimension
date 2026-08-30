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

"""Dialog: optionally exclude an ancestor of the directory delaying a slow scan."""

from __future__ import annotations

from .qt import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


class SlowScanIgnoreDialog(QDialog):
    """Offer optional excludes for an ancestor of the hot scan directory.

    Candidates are ordered top-level → hot leaf. The top-level entry is selected
    by default. Checkboxes start unchecked; **Accept** enables only after at
    least one checkbox is checked. **Continue** dismisses without applying
    excludes (and does not permanently suppress the top-level ancestor).
    """

    def __init__(self, ancestors: list[str], *, hot_path: str = "", parent=None):
        QDialog.__init__(self, parent)
        if not ancestors:
            raise ValueError("ancestors must be non-empty")
        self.setWindowTitle("Slow project scan")
        self.setModal(True)
        self.resize(560, 260)
        self.__ancestors = list(ancestors)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Project scan is taking longer than 30 seconds.\nMost time is currently spent reading this directory:",
                self,
            )
        )
        hot_label = QLabel(hot_path or ancestors[-1], self)
        hot_label.setWordWrap(True)
        layout.addWidget(hot_label)

        layout.addWidget(
            QLabel(
                "Choose which directory to exclude (top-level is recommended):",
                self,
            )
        )
        self.pathCombo = QComboBox(self)
        for path in self.__ancestors:
            self.pathCombo.addItem(path)
        self.pathCombo.setCurrentIndex(0)
        layout.addWidget(self.pathCombo)

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

    def selectedDirectory(self) -> str:
        """Relative directory currently chosen in the ancestor combo."""
        return self.pathCombo.currentText().strip()

    def selectedExcludes(self) -> tuple[list[str], list[str]]:
        """Return ``(excludeFromAnalysis, excludeFromProjectTree)`` for the choice."""
        relative_dir = self.selectedDirectory()
        analysis: list[str] = []
        tree: list[str] = []
        if not relative_dir:
            return analysis, tree
        if self.analysisCheck.isChecked():
            analysis.append(relative_dir)
        if self.treeCheck.isChecked():
            tree.append(relative_dir)
        return analysis, tree
