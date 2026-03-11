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

"""Codimension coverage results viewer."""

import os.path

from ui.itemdelegates import NoOutlineHeightDelegate
from ui.labels import HeaderFitPathLabel, HeaderLabel
from ui.qt import (
    QAction,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPalette,
    QSize,
    QSizePolicy,
    Qt,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from ui.spacers import ToolBarExpandingSpacer
from utils.globals import GlobalData
from utils.pixmapcache import getIcon


class CoverageResultViewer(QWidget):
    """Coverage results viewer."""

    def __init__(self, ide, pluginHomeDir, parent=None):
        QWidget.__init__(self, parent)
        self.__results = None
        self.__ide = ide
        self.__pluginHomeDir = pluginHomeDir

        self.__noneLabel = QLabel("\nNo results available")
        self.__noneLabel.setFrameShape(QFrame.StyledPanel)
        self.__noneLabel.setAlignment(Qt.AlignHCenter)
        font = self.__noneLabel.font()
        font.setPointSize(font.pointSize() + 4)
        self.__noneLabel.setFont(font)
        self.__noneLabel.setAutoFillBackground(True)
        noneLabelPalette = self.__noneLabel.palette()
        noneLabelPalette.setColor(QPalette.Background, GlobalData().skin["nolexerPaper"])
        self.__noneLabel.setPalette(noneLabelPalette)

        self.clearButton = QAction(getIcon("trash.png"), "Clear", self)
        self.clearButton.triggered.connect(self.clear)

        self.toolbar = QToolBar(self)
        self.toolbar.setOrientation(Qt.Vertical)
        self.toolbar.setMovable(False)
        self.toolbar.setAllowedAreas(Qt.RightToolBarArea)
        self.toolbar.setIconSize(QSize(16, 16))
        self.toolbar.setFixedWidth(28)
        self.toolbar.setContentsMargins(0, 0, 0, 0)
        self.toolbar.addWidget(ToolBarExpandingSpacer(self.toolbar))
        self.toolbar.addAction(self.clearButton)

        self.__resultsTree = QTreeWidget(self)
        self.__resultsTree.setAlternatingRowColors(True)
        self.__resultsTree.setRootIsDecorated(True)
        self.__resultsTree.setItemsExpandable(True)
        self.__resultsTree.setUniformRowHeights(True)
        self.__resultsTree.setItemDelegate(NoOutlineHeightDelegate(4))
        self.__resultsTree.setHeaderLabels(["File", "Coverage %", "Lines"])
        self.__resultsTree.itemActivated.connect(self.__resultActivated)

        self.__fileLabel = HeaderFitPathLabel(None, self)
        self.__fileLabel.setAlignment(Qt.AlignLeft)
        self.__fileLabel.setMinimumWidth(50)
        self.__fileLabel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.__fileLabel.doubleClicked.connect(self.onPathLabelDoubleClick)

        self.__timestampLabel = HeaderLabel()
        self.__labelLayout = QHBoxLayout()
        self.__labelLayout.setSpacing(4)
        self.__labelLayout.addWidget(self.__fileLabel)
        self.__labelLayout.addWidget(self.__timestampLabel)

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
        self.clearButton.setEnabled(self.__results is not None)

    def clear(self):
        """Clears the results."""
        self.__results = None
        self.__noneLabel.setVisible(True)
        self.__fileLabel.setVisible(False)
        self.__timestampLabel.setVisible(False)
        self.__resultsTree.setVisible(False)
        self.__resultsTree.clear()
        self.__updateButtons()

    def onPathLabelDoubleClick(self):
        """Opens the test file on double click."""
        if self.__results and self.__ide:
            self.__ide.mainWindow.openFile(self.__results["FileName"], -1)

    def __resultActivated(self, item, column):
        """Opens the file at first missing line when activated."""
        del column
        if not self.__results or not item.parent():
            return
        fileData = item.data(0, Qt.UserRole)
        if not fileData:
            return
        path = fileData.get("path", "")
        missing = fileData.get("missing_lines", [])
        lineNo = missing[0] if missing else -1
        if path and os.path.exists(path):
            self.__ide.mainWindow.openFile(path, lineNo)

    def showResults(self, results):
        """Populates the coverage results."""
        self.clear()
        self.__noneLabel.setVisible(False)
        self.__fileLabel.setVisible(True)
        self.__timestampLabel.setVisible(True)
        self.__resultsTree.setVisible(True)

        self.__results = results
        self.__updateButtons()

        if "ProcessError" in results:
            item = QTreeWidgetItem(["Error", "", results["ProcessError"]])
            self.__resultsTree.addTopLevelItem(item)
            return

        tooltip = " ".join(["Coverage for", os.path.basename(results["FileName"]), "at", results["Timestamp"]])
        self.__ide.sideBars["bottom"].setTabToolTip("coverage", tooltip)

        self.__fileLabel.setPath(results["FileName"])
        self.__timestampLabel.setText(results["Timestamp"])

        totals = results.get("Totals", {})
        totalPercent = totals.get("percent_covered", 0)
        totalStmt = totals.get("num_statements", 0)
        totalCovered = totals.get("covered_lines", 0)

        summaryText = f"Total: {totalPercent:.1f}% ({totalCovered}/{totalStmt} lines)"
        parent = QTreeWidgetItem([summaryText, "", ""])
        self.__resultsTree.addTopLevelItem(parent)

        filesData = results.get("Files", [])
        for f in filesData:
            path = f.get("path", "")
            percent = f.get("percent", 0)
            numStmt = f.get("num_statements", 0)
            covered = f.get("covered_lines", 0)
            shortPath = os.path.basename(path) if path else "?"
            linesText = f"{covered}/{numStmt}"
            item = QTreeWidgetItem([shortPath, f"{percent:.1f}%", linesText])
            item.setData(0, Qt.UserRole, f)
            item.setToolTip(0, path)
            parent.addChild(item)

        parent.setExpanded(True)
        self.__resultsTree.header().resizeSections(QHeaderView.ResizeToContents)
