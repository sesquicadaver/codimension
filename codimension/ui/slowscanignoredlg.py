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

"""Dialog: pick top-level dirs to exclude after a slow project scan."""

from __future__ import annotations

from .qt import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class SlowScanIgnoreDialog(QDialog):
    """Offer top-level directories for analysis and/or project-tree exclusion."""

    def __init__(self, dir_names: list[str], parent=None):
        QDialog.__init__(self, parent)
        self.setWindowTitle("Slow project scan")
        self.setModal(True)
        self.resize(520, 360)
        self.__rows: list[tuple[str, QCheckBox, QCheckBox]] = []

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Project scan is taking longer than 30 seconds.\n"
                "Select directories to ignore. You can change this later in Project Properties.",
                self,
            )
        )

        header = QWidget(self)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        name_hdr = QLabel("Directory", header)
        name_hdr.setMinimumWidth(220)
        header_layout.addWidget(name_hdr)
        header_layout.addWidget(QLabel("Analysis", header))
        header_layout.addWidget(QLabel("Project tree", header))
        header_layout.addStretch(1)
        layout.addWidget(header)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        body = QWidget(scroll)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)

        for name in dir_names:
            row = QWidget(body)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 2, 0, 2)
            label = QLabel(name, row)
            label.setMinimumWidth(220)
            analysis_cb = QCheckBox(row)
            analysis_cb.setChecked(True)
            analysis_cb.setToolTip("Exclude from analysis / filesList / watcher")
            tree_cb = QCheckBox(row)
            tree_cb.setChecked(True)
            tree_cb.setToolTip("Hide from Project tree UI")
            row_layout.addWidget(label)
            row_layout.addWidget(analysis_cb)
            row_layout.addWidget(tree_cb)
            row_layout.addStretch(1)
            body_layout.addWidget(row)
            self.__rows.append((name, analysis_cb, tree_cb))

        body_layout.addStretch(1)
        scroll.setWidget(body)
        layout.addWidget(scroll)

        buttons = QDialogButtonBox(self)
        apply_btn = buttons.addButton("Apply and rescan", QDialogButtonBox.AcceptRole)
        continue_btn = buttons.addButton("Continue scanning", QDialogButtonBox.RejectRole)
        assert apply_btn is not None
        assert continue_btn is not None
        apply_btn.clicked.connect(self.accept)
        continue_btn.clicked.connect(self.reject)
        layout.addWidget(buttons)

    def selectedExcludes(self) -> tuple[list[str], list[str]]:
        """Return ``(excludeFromAnalysis, excludeFromProjectTree)`` selections."""
        analysis: list[str] = []
        tree: list[str] = []
        for name, analysis_cb, tree_cb in self.__rows:
            if analysis_cb.isChecked():
                analysis.append(name)
            if tree_cb.isChecked():
                tree.append(name)
        return analysis, tree
