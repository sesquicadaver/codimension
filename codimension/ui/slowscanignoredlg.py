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

"""Dialog: ignore the directory that is delaying a slow project scan."""

from __future__ import annotations

from .qt import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    Qt,
    QVBoxLayout,
)


class SlowScanIgnoreDialog(QDialog):
    """Offer to ignore the hot directory delaying the project scan."""

    def __init__(self, relative_dir: str, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowTitle("Slow project scan")
        self.setModal(True)
        self.resize(520, 200)
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
        self.analysisCheck.setChecked(True)
        self.analysisCheck.setToolTip("Exclude from analysis / filesList / watcher")
        self.treeCheck = QCheckBox("Hide from project tree", self)
        self.treeCheck.setChecked(True)
        self.treeCheck.setToolTip("Hide from Project tree UI")
        checks.addWidget(self.analysisCheck)
        checks.addWidget(self.treeCheck)
        checks.addStretch(1)
        layout.addLayout(checks)

        layout.addWidget(
            QLabel(
                "You can change excludes later in Project Properties.",
                self,
            )
        )

        buttons = QDialogButtonBox(self)
        ignore_btn = buttons.addButton("Ignore and rescan", QDialogButtonBox.AcceptRole)
        continue_btn = buttons.addButton("Continue scanning", QDialogButtonBox.RejectRole)
        assert ignore_btn is not None
        assert continue_btn is not None
        ignore_btn.clicked.connect(self.accept)
        continue_btn.clicked.connect(self.reject)
        layout.addWidget(buttons)

    def selectedExcludes(self) -> tuple[list[str], list[str]]:
        """Return ``(excludeFromAnalysis, excludeFromProjectTree)`` for this directory."""
        analysis: list[str] = []
        tree: list[str] = []
        if self.analysisCheck.isChecked():
            analysis.append(self.__relative_dir)
        if self.treeCheck.isChecked():
            tree.append(self.__relative_dir)
        return analysis, tree
