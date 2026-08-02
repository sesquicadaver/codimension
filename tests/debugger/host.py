# -*- coding: utf-8 -*-
"""Thin debugger host for session-first e2e and mixin routing (T101/T110).

Avoids full CodimensionMainWindow: IO console surface for RunManager plus
chrome stubs required by MainWindowDebuggerMixin.switchDebugMode.
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


class _StubChrome:
    """Toolbar / status / action stub with visibility and enable flags."""

    def __init__(self, name: str = ""):
        self.name = name
        self.visible = True
        self.enabled = True
        self.text = ""

    def setVisible(self, value: bool) -> None:
        """Record visibility (mixin switchDebugMode)."""
        self.visible = bool(value)

    def setEnabled(self, value: bool) -> None:
        """Record enabled state."""
        self.enabled = bool(value)

    def setText(self, value: str) -> None:
        """Record label text (status bar)."""
        self.text = str(value)

    def isVisible(self) -> bool:
        """Qt-compatible visibility query."""
        return self.visible

    def isEnabled(self) -> bool:
        """Qt-compatible enabled query."""
        return self.enabled


class _StubSideBar:
    """Right sidebar surface used by MainWindowDebuggerMixin."""

    def __init__(self):
        self.enabled_tabs: dict[str, bool] = {}
        self.tab_texts: dict[str, str] = {}
        self.current: str | None = "fileoutline"
        self.shown = False
        self.minimized = False

    def setTabEnabled(self, name: str, enabled: bool) -> None:
        """Enable/disable a named tab."""
        self.enabled_tabs[name] = bool(enabled)

    def setTabText(self, name: str, text: str) -> None:
        """Update tab caption."""
        self.tab_texts[name] = str(text)

    def show(self) -> None:
        """Show sidebar."""
        self.shown = True

    def raise_(self) -> None:
        """Bring sidebar to front (Qt raise_)."""
        return None

    def setCurrentTab(self, name: str) -> None:
        """Select tab by name."""
        self.current = name

    def isMinimized(self) -> bool:
        """Whether sidebar is minimized."""
        return self.minimized

    def currentTabName(self) -> str | None:
        """Active tab name."""
        return self.current


class _StubPanel:
    """Debugger context / exceptions / call-trace panel stub."""

    def clear(self) -> None:
        """Clear panel contents."""
        return None

    def switchControl(self, enabled: bool) -> None:
        """Toggle panel control (state-change path)."""
        del enabled


def _install_mixin_chrome(host) -> None:
    """Attach status bar, toolbar, sidebar, and panel stubs (PRD R2)."""
    host.sbDebugState = _StubChrome("sbDebugState")
    host.sbLanguage = _StubChrome("sbLanguage")
    host.sbEncoding = _StubChrome("sbEncoding")
    host.sbEol = _StubChrome("sbEol")

    for name in (
        "_dbgStop",
        "_dbgRestart",
        "_dbgGo",
        "_dbgNext",
        "_dbgStepInto",
        "_dbgRunToLine",
        "_dbgReturn",
        "_dbgJumpToCurrent",
        "_dbgDumpSettingsAct",
    ):
        setattr(host, name, _StubChrome(name))

    for name in (
        "_debugStopAct",
        "_debugRestartAct",
        "_debugContinueAct",
        "_debugStepOverAct",
        "_debugStepInAct",
        "_debugStepOutAct",
        "_debugRunToCursorAct",
        "_debugJumpToCurrentAct",
        "_debugDumpSettingsAct",
        "_debugDumpSettingsEnvAct",
    ):
        setattr(host, name, _StubChrome(name))

    host._rightSideBar = _StubSideBar()
    host.debuggerContext = _StubPanel()
    host.debuggerExceptions = _StubPanel()
    host.debuggerCallTrace = _StubPanel()


def create_mixin_host(parent=None):
    """Build MixinDebuggerHost with MainWindowDebuggerMixin MRO (T110).

    Lazy-imports the mixin so collection-time stubs cannot break import of
    this module.
    """
    from ui.mainwindow_debug import MainWindowDebuggerMixin

    class MixinDebuggerHost(MainWindowDebuggerMixin, QObject):
        """Composed host: mixin routing + RunManager IO console surface."""

        debugModeChanged = pyqtSignal(bool)

        def __init__(self, parent=None):
            """Initialize mixin state, chrome stubs, and IO console list."""
            QObject.__init__(self, parent)
            MainWindowDebuggerMixin.__init__(self)
            _install_mixin_chrome(self)
            self._consoles: list[FakeIOConsole] = []
            self.status_messages: list[str] = []
            self.switch_calls: list[bool] = []
            self.finished_consoles: list[object] = []
            self._debugger = None
            self._runManager = None

        def switchDebugMode(self, newState: bool) -> None:
            """Track calls then delegate to MainWindowDebuggerMixin."""
            if self.debugMode == newState:
                return
            self.switch_calls.append(newState)
            MainWindowDebuggerMixin.switchDebugMode(self, newState)

        def updateRunDebugButtons(self) -> None:
            """No-op: real implementation lives on CodimensionMainWindow."""
            return None

        def _removeCurrentDebugLineHighlight(self) -> None:
            """No-op: no editors manager on the thin host."""
            return None

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

    return MixinDebuggerHost(parent)


# Backward-compatible alias used by session helpers / docs.
DebuggerHost = create_mixin_host
