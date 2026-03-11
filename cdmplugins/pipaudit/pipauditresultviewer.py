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

"""Codimension pip-audit results viewer."""

from ui.itemdelegates import NoOutlineHeightDelegate
from ui.labels import HeaderLabel
from ui.qt import (
    QAction,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPalette,
    QSize,
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


class PipAuditResultViewer(QWidget):
    """pip-audit results viewer."""

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
        self.__resultsTree.setHeaderLabels(["Package", "Version", "CVE", "Fix versions"])
        self.__resultsTree.itemActivated.connect(self.__resultActivated)

        self.__timestampLabel = HeaderLabel()
        self.__labelLayout = QHBoxLayout()
        self.__labelLayout.setSpacing(4)
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
        self.__timestampLabel.setVisible(False)
        self.__resultsTree.setVisible(False)
        self.__resultsTree.clear()
        self.__updateButtons()

    def __resultActivated(self, item, column):
        """Handles activation - pip-audit has no file/line to navigate to."""
        del column, item

    def showResults(self, results):
        """Populates the audit results."""
        self.clear()
        self.__noneLabel.setVisible(False)
        self.__timestampLabel.setVisible(True)
        self.__resultsTree.setVisible(True)

        self.__results = results
        self.__updateButtons()

        if "ProcessError" in results:
            item = QTreeWidgetItem(["Error", "", "", results["ProcessError"]])
            self.__resultsTree.addTopLevelItem(item)
            return

        tooltip = " ".join(["pip-audit results at", results["Timestamp"]])
        self.__ide.sideBars["bottom"].setTabToolTip("pipaudit", tooltip)

        self.__timestampLabel.setText(results["Timestamp"])

        packages = results.get("Packages", [])
        if packages:
            parent = QTreeWidgetItem([f"Vulnerabilities ({len(packages)})", "", "", ""])
            self.__resultsTree.addTopLevelItem(parent)
            for p in packages:
                fixVer = ", ".join(p.get("fix_versions", []))
                item = QTreeWidgetItem(
                    [
                        p.get("name", ""),
                        str(p.get("version", "")),
                        p.get("cve", ""),
                        fixVer,
                    ]
                )
                desc = p.get("description", "")
                if desc:
                    item.setToolTip(2, desc[:500] + ("..." if len(desc) > 500 else ""))
                parent.addChild(item)
            parent.setExpanded(True)
        else:
            item = QTreeWidgetItem(["", "", "", "No known vulnerabilities found"])
            self.__resultsTree.addTopLevelItem(item)

        self.__resultsTree.header().resizeSections(QHeaderView.ResizeToContents)
