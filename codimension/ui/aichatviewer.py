# -*- coding: utf-8 -*-
#
# codimension - on-demand AI chat panel
# Copyright (C) 2026  Codimension Team
# The license is described in the LICENSE file at the root directory.
#

"""AI Chat bottom tab: shown on request, sends free-form prompts."""

from __future__ import annotations

from core.ai_tasks import AiTaskKind, AiTaskRequest
from utils.colorfont import getZoomedMonoFont
from utils.pixmapcache import getIcon

from .aiworker import AiTaskDriver
from .qt import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    Qt,
    QVBoxLayout,
    QWidget,
)


class AiChatViewer(QWidget):
    """Simple chat UI backed by :class:`AiTaskDriver`."""

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self.__history: list[tuple[str, str]] = []
        self.__driver = AiTaskDriver(self)
        self.__driver.sigProgress.connect(self.__onProgress)
        self.__driver.sigFinished.connect(self.__onFinished)
        self.__driver.sigFailed.connect(self.__onFailed)
        self.__context = ""
        self.__createLayout()
        self.onTextZoomChanged()

    def onTextZoomChanged(self) -> None:
        """Apply IDE mono zoom."""
        self.__log.setFont(getZoomedMonoFont())
        self.__input.setFont(getZoomedMonoFont())

    def __createLayout(self) -> None:
        self.__status = QLabel("AI Chat — configure a live provider in AI settings", self)
        self.__status.setWordWrap(True)
        self.__log = QPlainTextEdit(self)
        self.__log.setReadOnly(True)
        self.__input = QLineEdit(self)
        self.__input.setPlaceholderText("Ask about the current buffer / project…")
        self.__input.returnPressed.connect(self.__send)
        self.__sendBtn = QPushButton(getIcon("sendioup.png"), "Send", self)
        self.__sendBtn.clicked.connect(self.__send)
        self.__clearBtn = QPushButton(getIcon("trash.png"), "Clear", self)
        self.__clearBtn.clicked.connect(self.clear)

        row = QHBoxLayout()
        row.addWidget(self.__input)
        row.addWidget(self.__sendBtn)
        row.addWidget(self.__clearBtn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.__status)
        layout.addWidget(self.__log)
        layout.addLayout(row)

    def setContextNote(self, note: str) -> None:
        """Optional context (current file excerpt) prepended to prompts."""
        self.__context = (note or "").strip()

    def clear(self) -> None:
        """Clear transcript and history."""
        self.__history.clear()
        self.__log.clear()
        self.__status.setText("AI Chat cleared")

    def focusInput(self) -> None:
        """Focus the prompt field."""
        self.__input.setFocus(Qt.OtherFocusReason)

    def __append(self, role: str, text: str) -> None:
        self.__log.appendPlainText(f"{role}: {text}\n")

    def __send(self) -> None:
        message = self.__input.text().strip()
        if not message:
            return
        if self.__driver.isInProcess():
            self.__status.setText("Wait for the current reply…")
            return
        self.__input.clear()
        self.__append("You", message)
        request = AiTaskRequest(
            kind=AiTaskKind.CHAT,
            title="AI Chat",
            chat_message=message,
            chat_history=tuple(self.__history),
            source=self.__context,
        )
        self.__history.append(("user", message))
        err = self.__driver.start(request)
        if err:
            self.__status.setText(err)
            return
        self.__status.setText("Waiting for model…")
        self.__sendBtn.setEnabled(False)

    def __onProgress(self, message: str) -> None:
        self.__status.setText(message)

    def __onFinished(self, result) -> None:
        self.__sendBtn.setEnabled(True)
        text = getattr(result, "text", "") or ""
        self.__history.append(("assistant", text))
        self.__append("AI", text)
        backend = getattr(result, "backend_name", "")
        self.__status.setText(f"Done [{backend}]" if backend else "Done")

    def __onFailed(self, message: str) -> None:
        self.__sendBtn.setEnabled(True)
        self.__append("Error", message)
        self.__status.setText(message)
