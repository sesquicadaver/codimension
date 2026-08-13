# -*- coding: utf-8 -*-
#
# codimension - AI analysis result panel
# Copyright (C) 2026  Codimension Team
# The license is described in the LICENSE file at the root directory.
#

"""Bottom-bar panel for AI analysis / docstring results (with Save)."""

from __future__ import annotations

import os
from datetime import datetime

from utils.colorfont import getZoomedMonoFont
from utils.pixmapcache import getIcon

from .qt import (
    QAction,
    QDir,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QSize,
    Qt,
    QToolBar,
    QVBoxLayout,
    QWidget,
)
from .spacers import ToolBarExpandingSpacer


class AiResultViewer(QWidget):
    """Read-only text panel for AI reports with Copy / Save / Clear."""

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self.__title = ""
        self.__last_kind = ""
        self.__last_symbol = ""
        self.__last_file = ""
        self.__createLayout()
        self.onTextZoomChanged()
        self.__updateButtons()

    def onTextZoomChanged(self) -> None:
        """Apply IDE mono zoom to the result view."""
        self.__text.setFont(getZoomedMonoFont())

    def __createLayout(self) -> None:
        self.__status = QLabel("No AI results yet", self)
        self.__status.setWordWrap(True)

        self.__text = QPlainTextEdit(self)
        self.__text.setReadOnly(True)
        self.__text.setLineWrapMode(QPlainTextEdit.WidgetWidth)

        self.__saveAct = QAction(getIcon("savemenu.png"), "Save report…", self)
        self.__saveAct.triggered.connect(self.__save)
        self.__copyAct = QAction(getIcon("copymenu.png"), "Copy", self)
        self.__copyAct.triggered.connect(self.__text.copy)
        self.__clearAct = QAction(getIcon("trash.png"), "Clear", self)
        self.__clearAct.triggered.connect(self.clear)

        self.__applyDocAct = QAction(getIcon("edit.png"), "Apply docstring", self)
        self.__applyDocAct.setToolTip("Apply the last docstring result into the editor")
        self.__applyDocAct.setEnabled(False)

        toolbar = QToolBar(self)
        toolbar.setOrientation(Qt.Vertical)  # type: ignore[attr-defined]
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(16, 16))
        toolbar.setFixedWidth(28)
        toolbar.addAction(self.__saveAct)
        toolbar.addAction(self.__copyAct)
        toolbar.addAction(self.__applyDocAct)
        toolbar.addWidget(ToolBarExpandingSpacer(toolbar))
        toolbar.addAction(self.__clearAct)

        text_col = QWidget(self)
        col = QVBoxLayout(text_col)
        col.setContentsMargins(4, 4, 4, 4)
        col.setSpacing(4)
        col.addWidget(self.__status)
        col.addWidget(self.__text)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(toolbar)
        layout.addWidget(text_col)

    def applyDocstringAction(self) -> QAction:
        """Expose Apply action so MainWindow can connect editor apply."""
        return self.__applyDocAct

    def showResult(
        self,
        title: str,
        text: str,
        *,
        kind: str = "",
        file_path: str = "",
        symbol_name: str = "",
        backend_name: str = "",
    ) -> None:
        """Replace panel content with a new AI result."""
        self.__title = title or "AI result"
        self.__last_kind = kind
        self.__last_file = file_path
        self.__last_symbol = symbol_name
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        meta = f"{self.__title} — {stamp}"
        if backend_name:
            meta += f" [{backend_name}]"
        self.__status.setText(meta)
        self.__text.setPlainText(text or "")
        self.__applyDocAct.setEnabled(kind == "docstring" and bool(symbol_name))
        self.__updateButtons()

    def appendStatus(self, message: str) -> None:
        """Update the status line (progress)."""
        self.__status.setText(message)

    def clear(self) -> None:
        """Clear the panel."""
        self.__title = ""
        self.__last_kind = ""
        self.__last_file = ""
        self.__last_symbol = ""
        self.__status.setText("No AI results yet")
        self.__text.clear()
        self.__applyDocAct.setEnabled(False)
        self.__updateButtons()

    def getText(self) -> str:
        """Return current report text."""
        return self.__text.toPlainText()

    def lastDocstringTarget(self) -> tuple[str, str, str]:
        """Return ``(kind, file_path, symbol_name)`` for Apply."""
        return self.__last_kind, self.__last_file, self.__last_symbol

    def __updateButtons(self) -> None:
        has = bool(self.__text.toPlainText().strip())
        self.__saveAct.setEnabled(has)
        self.__copyAct.setEnabled(has)
        self.__clearAct.setEnabled(has)

    def __save(self) -> None:
        """Save report text to a user-chosen file."""
        text = self.getText()
        if not text.strip():
            return
        suggested = os.path.join(QDir.homePath(), "codimension-ai-report.md")
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save AI report",
            suggested,
            "Markdown (*.md);;Text (*.txt);;All files (*)",
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
            if not text.endswith("\n"):
                handle.write("\n")
        self.__status.setText(f"Saved: {path}")
