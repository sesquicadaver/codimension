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

"""Codimension TODO panel viewer."""

import os.path

from ui.qt import (
    QWidget,
    QLabel,
    QPalette,
    QAction,
    Qt,
    QHBoxLayout,
    QVBoxLayout,
    QToolBar,
    QSize,
    QTreeWidget,
    QTreeWidgetItem,
    QHeaderView,
    QFrame,
    QComboBox,
)
from ui.itemdelegates import NoOutlineHeightDelegate
from ui.labels import HeaderLabel
from ui.spacers import ToolBarExpandingSpacer
from utils.pixmapcache import getIcon
from utils.globals import GlobalData


class TodoPanelViewer(QWidget):
    """TODO/FIXME panel viewer."""

    FILTER_ALL = "All"
    FILTER_TODO = "TODO"
    FILTER_FIXME = "FIXME"
    FILTER_XXX = "XXX"
    FILTER_HACK = "HACK"

    def __init__(self, ide, pluginHomeDir, parent=None):
        QWidget.__init__(self, parent)
        self.__results = []
        self.__ide = ide
        self.__pluginHomeDir = pluginHomeDir

        self.__noneLabel = QLabel("\nNo results. Scan project or open file.")
        self.__noneLabel.setFrameShape(QFrame.StyledPanel)
        self.__noneLabel.setAlignment(Qt.AlignHCenter)
        font = self.__noneLabel.font()
        font.setPointSize(font.pointSize() + 4)
        self.__noneLabel.setFont(font)
        self.__noneLabel.setAutoFillBackground(True)
        noneLabelPalette = self.__noneLabel.palette()
        noneLabelPalette.setColor(
            QPalette.Background, GlobalData().skin["nolexerPaper"]
        )
        self.__noneLabel.setPalette(noneLabelPalette)

        self.refreshButton = QAction(getIcon("run.png"), "Refresh", self)
        self.clearButton = QAction(getIcon("trash.png"), "Clear", self)
        self.clearButton.triggered.connect(self.clear)

        self.filterCombo = QComboBox(self)
        self.filterCombo.addItems(
            [
                self.FILTER_ALL,
                self.FILTER_TODO,
                self.FILTER_FIXME,
                self.FILTER_XXX,
                self.FILTER_HACK,
            ]
        )
        self.filterCombo.currentTextChanged.connect(self.__applyFilter)

        self.toolbar = QToolBar(self)
        self.toolbar.setOrientation(Qt.Vertical)
        self.toolbar.setMovable(False)
        self.toolbar.setAllowedAreas(Qt.RightToolBarArea)
        self.toolbar.setIconSize(QSize(16, 16))
        self.toolbar.setFixedWidth(28)
        self.toolbar.setContentsMargins(0, 0, 0, 0)
        self.toolbar.addWidget(ToolBarExpandingSpacer(self.toolbar))
        self.toolbar.addAction(self.refreshButton)
        self.toolbar.addAction(self.clearButton)

        self.__resultsTree = QTreeWidget(self)
        self.__resultsTree.setAlternatingRowColors(True)
        self.__resultsTree.setRootIsDecorated(True)
        self.__resultsTree.setItemsExpandable(True)
        self.__resultsTree.setUniformRowHeights(True)
        self.__resultsTree.setItemDelegate(NoOutlineHeightDelegate(4))
        self.__resultsTree.setHeaderLabels(["File", "Line", "Tag", "Text"])
        self.__resultsTree.itemActivated.connect(self.__resultActivated)

        self.__filterLabel = HeaderLabel("Filter:")
        self.__labelLayout = QHBoxLayout()
        self.__labelLayout.setSpacing(4)
        self.__labelLayout.addWidget(self.__filterLabel)
        self.__labelLayout.addWidget(self.filterCombo)

        self.__vLayout = QVBoxLayout()
        self.__vLayout.setSpacing(4)
        self.__vLayout.addLayout(self.__labelLayout)
        self.__vLayout.addWidget(self.__resultsTree)

        self.__hLayout = QHBoxLayout()
        self.__hLayout.setContentsMargins(0, 0, 0, 0)
        self.__hLayout.setSpacing(0)
        self.__hLayout.addWidget(self.toolbar)
        self.__hLayout.addWidget(self.__noneLabel)
        self.__hLayout.addLayout(self.__vLayout)

        self.setLayout(self.__hLayout)
        self.__updateButtons()

    def __updateButtons(self):
        """Updates the toolbar buttons."""
        has_results = bool(self.__results)
        self.clearButton.setEnabled(has_results)

    def clear(self):
        """Clears the results."""
        self.__results = []
        self.__noneLabel.setVisible(True)
        self.__filterLabel.setVisible(False)
        self.filterCombo.setVisible(False)
        self.__resultsTree.setVisible(False)
        self.__resultsTree.clear()
        self.__updateButtons()

    def __resultActivated(self, item, column):
        """Navigates to the file:line when activated."""
        del column
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        file_path = data.get("file", "")
        line_no = data.get("line", -1)
        if file_path and os.path.exists(file_path):
            self.__ide.mainWindow.openFile(file_path, line_no)

    def __applyFilter(self):
        """Re-populates tree with current filter."""
        self.__populateTree()

    def __populateTree(self):
        """Populates the tree from __results with current filter."""
        self.__resultsTree.clear()
        filter_tag = self.filterCombo.currentText()
        filtered = (
            self.__results
            if filter_tag == self.FILTER_ALL
            else [r for r in self.__results if r.get("tag") == filter_tag]
        )

        if not filtered:
            return

        by_file = {}
        for r in filtered:
            f = r.get("file", "")
            if f not in by_file:
                by_file[f] = []
            by_file[f].append(r)

        for file_path in sorted(by_file.keys()):
            hits = by_file[file_path]
            short_name = os.path.basename(file_path)
            parent = QTreeWidgetItem(
                [short_name, "", "", f"{len(hits)} item(s)"]
            )
            parent.setToolTip(0, file_path)
            self.__resultsTree.addTopLevelItem(parent)
            for h in hits:
                item = QTreeWidgetItem(
                    [
                        "",
                        str(h.get("line", "")),
                        h.get("tag", ""),
                        (h.get("text", "") or "")[:80],
                    ]
                )
                item.setData(0, Qt.UserRole, h)
                item.setToolTip(3, h.get("text", ""))
                parent.addChild(item)
            parent.setExpanded(True)

        self.__resultsTree.header().resizeSections(QHeaderView.ResizeToContents)

    def hasResults(self):
        """True if the panel has scan results."""
        return bool(self.__results)

    def showResults(self, results):
        """Populates the panel with scan results."""
        self.__results = results
        self.__noneLabel.setVisible(False)
        self.__filterLabel.setVisible(True)
        self.filterCombo.setVisible(True)
        self.__resultsTree.setVisible(True)
        self.__updateButtons()
        self.__populateTree()

    def setRefreshCallback(self, callback):
        """Sets the refresh button callback."""
        try:
            self.refreshButton.triggered.disconnect()
        except TypeError:
            pass
        self.refreshButton.triggered.connect(callback)
