# -*- coding: utf-8 -*-
"""Thin debugger host for session-first e2e (Phase 0 / T101).

Avoids full CodimensionMainWindow: only the surface that RunManager and
CodimensionDebugger call during a redirected debug session.
"""

from __future__ import annotations

from datetime import datetime

# Prefer PyQt5 directly so collection-time ui.qt stubs cannot break this module.
from PyQt5.QtCore import QObject, pyqtSignal


class _IdeMessage:
    """Minimal stand-in for RedirectedIOConsole IDE message objects."""

    __slots__ = ("timestamp", "text")

    def __init__(self, text: str):
        self.text = text
        self.timestamp = datetime.now()


class FakeIOConsole(QObject):
    """Minimal IO console stub used instead of IOConsoleWidget (no skin)."""

    sigUserInput = pyqtSignal(str, str)
    sigKillIOConsoleProcess = pyqtSignal(str)
    sigSettingsUpdated = pyqtSignal()
    sigCloseIOConsole = pyqtSignal(int)

    def __init__(self, procuuid: str, kind: int, parent=None):
        """Bind process id and run kind (RUN/DEBUG/PROFILE)."""
        QObject.__init__(self, parent)
        self.procuuid = procuuid
        self.kind = kind
        self.messages: list[str] = []

    def onReuse(self, procuuid: str) -> None:
        """Reuse console for another process id."""
        self.procuuid = procuuid

    def clear(self) -> None:
        """Clear stored IDE/stdout/stderr messages."""
        self.messages.clear()

    def appendIDEMessage(self, message: str) -> _IdeMessage:
        """Record an IDE status line; return object with ``timestamp``."""
        self.messages.append(f"IDE:{message}")
        return _IdeMessage(message)

    def appendStdoutMessage(self, procuuid: str, message: str) -> None:
        """Record stdout from the debuggee (RunManager signal signature)."""
        del procuuid
        self.messages.append(f"OUT:{message}")

    def appendStderrMessage(self, procuuid: str, message: str) -> None:
        """Record stderr from the debuggee (RunManager signal signature)."""
        del procuuid
        self.messages.append(f"ERR:{message}")

    def input(self, procuuid: str, prompt: str, echo: int) -> None:
        """Ignore raw-input requests in headless session tests."""
        del procuuid, prompt, echo

    def scriptFinished(self) -> None:
        """RunManager calls this when the redirected process ends."""
        return None

    def sessionStopped(self) -> None:
        """Optional IOConsoleWidget hook — no-op for the stub."""
        return None


class DebuggerHost(QObject):
    """Stand-in for MainWindow surfaces used by debugger + RunManager."""

    debugModeChanged = pyqtSignal(bool)

    def __init__(self, parent=None):
        """Create empty console list and debug-mode flag."""
        QObject.__init__(self, parent)
        self.debugMode = False
        self._consoles: list[FakeIOConsole] = []
        self.status_messages: list[str] = []
        self.switch_calls: list[bool] = []
        self.finished_consoles: list[object] = []

    def switchDebugMode(self, newState: bool) -> None:
        """Toggle debug mode without touching real toolbars/sidebars."""
        if self.debugMode == newState:
            return
        self.debugMode = newState
        self.switch_calls.append(newState)
        self.debugModeChanged.emit(newState)

    def addIOConsole(self, widget, consoleType) -> None:
        """Register a fake (or real) IO console widget."""
        del consoleType
        if widget not in self._consoles:
            self._consoles.append(widget)

    def getIOConsoles(self) -> list:
        """Return registered IO consoles (reuse path)."""
        return list(self._consoles)

    def onReuseConsole(self, widget, kind) -> None:
        """No-op reuse hook for Settings ioconsolereuse paths."""
        del widget, kind

    def showStatusBarMessage(self, message: str, timeout: int = 0) -> None:
        """Capture status-bar messages from RunManager."""
        del timeout
        self.status_messages.append(message)

    def updateIOConsoleTooltip(self, procuuid: str, tooltip: str) -> None:
        """No-op tooltip update (bottom sidebar absent on host)."""
        del procuuid, tooltip

    def onConsoleFinished(self, widget) -> None:
        """Record finished console for assertions / cleanup."""
        self.finished_consoles.append(widget)
