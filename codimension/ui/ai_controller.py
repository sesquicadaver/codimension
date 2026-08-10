# -*- coding: utf-8 -*-
#
# codimension - MainWindow AI orchestration helpers
# Copyright (C) 2026  Codimension Team
# The license is described in the LICENSE file at the root directory.
#

"""Helpers used by MainWindow for AI analysis / docstring / chat panels."""

from __future__ import annotations

import logging
import os

from core.ai_docstring import apply_google_docstring
from core.ai_tasks import AiTaskKind, AiTaskRequest, list_project_py_files
from core.ai_ui import is_ai_ui_enabled
from utils.globals import GlobalData
from utils.pixmapcache import getIcon

from .aichatviewer import AiChatViewer
from .aiworker import AiTaskDriver
from .qt import QMessageBox


class AiWorkspaceController:
    """Owns the AI task driver and routes results into IDE panels."""

    def __init__(self, main_window):
        self._mw = main_window
        self._driver = AiTaskDriver(main_window)
        self._driver.sigProgress.connect(self._onProgress)
        self._driver.sigFinished.connect(self._onFinished)
        self._driver.sigFailed.connect(self._onFailed)

    def ensureResultTab(self) -> None:
        """Show the AI Result bottom tab."""
        self._mw.activateBottomTab("airesult")

    def ensureChatTab(self) -> None:
        """Create (once) and show the AI Chat bottom tab."""
        mw = self._mw
        if getattr(mw, "aiChatViewer", None) is None:
            mw.aiChatViewer = AiChatViewer(mw)
            mw._bottomSideBar.addTab(
                mw.aiChatViewer,
                getIcon("helpviewer.png"),
                "AI Chat",
                "aichat",
                4,
            )
        # Refresh context from current editor
        editor = self._currentEditor()
        if editor is not None and mw.aiChatViewer is not None:
            name = editor.getFileName() or "<buffer>"
            excerpt = (editor.text or "")[:4000]
            mw.aiChatViewer.setContextNote(f"Current file: {name}\n\n{excerpt}")
        mw.activateBottomTab("aichat")
        if mw.aiChatViewer is not None:
            mw.aiChatViewer.focusInput()

    def _currentEditor(self):
        try:
            widget = self._mw.em.currentWidget()
        except Exception:
            return None
        if widget is None:
            return None
        if hasattr(widget, "getEditor"):
            try:
                return widget.getEditor()
            except Exception:
                return None
        return None

    def _requireReady(self) -> bool:
        if not is_ai_ui_enabled():
            QMessageBox.information(
                self._mw,
                "AI disabled",
                "Enable AI via Options → Enable AI (experimental), then choose a live provider in AI settings…",
            )
            return False
        if self._driver.isInProcess():
            QMessageBox.information(self._mw, "AI busy", "An AI task is already running.")
            return False
        return True

    def startAnalyzeProject(self) -> None:
        """Analyze all project ``.py`` files (chunked + synthesis)."""
        if not self._requireReady():
            return
        project = GlobalData().project
        if project is None or not project.isLoaded():
            QMessageBox.warning(self._mw, "AI", "Open a project first.")
            return
        files = list_project_py_files(project.filesList, project.getProjectDir())
        if not files:
            QMessageBox.warning(self._mw, "AI", "No Python files found in the project.")
            return
        request = AiTaskRequest(
            kind=AiTaskKind.ANALYZE_PROJECT,
            title=f"Project analysis ({len(files)} modules)",
            project_files=files,
        )
        self._start(request)

    def startAnalyzeModule(self) -> None:
        """Analyze the current Python buffer / file."""
        if not self._requireReady():
            return
        editor = self._currentEditor()
        if editor is None or not getattr(editor, "isPythonBuffer", lambda: False)():
            QMessageBox.warning(self._mw, "AI", "Open a Python file to analyze the module.")
            return
        path = editor.getFileName() or "<buffer>"
        try:
            widget = self._mw.em.currentWidget()
            if widget is not None and hasattr(widget, "getShortName"):
                path = editor.getFileName() or widget.getShortName() or "<buffer>"
        except Exception:
            pass
        request = AiTaskRequest(
            kind=AiTaskKind.ANALYZE_MODULE,
            title=f"Module analysis: {os.path.basename(path)}",
            file_path=path,
            source=editor.text or "",
        )
        self._start(request)

    def startAnalyzeSymbol(self) -> None:
        """Analyze function/class under the cursor."""
        if not self._requireReady():
            return
        editor = self._currentEditor()
        if editor is None or not getattr(editor, "isPythonBuffer", lambda: False)():
            QMessageBox.warning(self._mw, "AI", "Open a Python file and place the cursor on a symbol.")
            return
        name = ""
        try:
            name = editor.getCurrentOrSelection()[0].strip()
        except Exception:
            name = ""
        if not name or not name.isidentifier():
            QMessageBox.warning(self._mw, "AI", "Place the cursor on a function or class name.")
            return
        path = editor.getFileName() or "<buffer>"
        request = AiTaskRequest(
            kind=AiTaskKind.ANALYZE_SYMBOL,
            title=f"Symbol analysis: {name}",
            file_path=path,
            source=editor.text or "",
            symbol_name=name,
        )
        self._start(request)

    def startDocstring(self) -> None:
        """Generate a Google-style docstring for the symbol under the cursor."""
        if not self._requireReady():
            return
        editor = self._currentEditor()
        if editor is None or not getattr(editor, "isPythonBuffer", lambda: False)():
            QMessageBox.warning(self._mw, "AI", "Open a Python file and select a function/class.")
            return
        try:
            name = editor.getCurrentOrSelection()[0].strip()
        except Exception:
            name = ""
        if not name or not name.isidentifier():
            QMessageBox.warning(self._mw, "AI", "Place the cursor on a function or class name.")
            return
        path = editor.getFileName() or "<buffer>"
        request = AiTaskRequest(
            kind=AiTaskKind.DOCSTRING,
            title=f"Docstring: {name}",
            file_path=path,
            source=editor.text or "",
            symbol_name=name,
        )
        self._start(request)

    def applyLastDocstring(self) -> None:
        """Apply the last docstring result into the current editor buffer."""
        viewer = getattr(self._mw, "aiResultViewer", None)
        if viewer is None:
            return
        kind, _file_path, symbol = viewer.lastDocstringTarget()
        if kind != "docstring" or not symbol:
            QMessageBox.information(self._mw, "AI", "No docstring result to apply.")
            return
        editor = self._currentEditor()
        if editor is None:
            QMessageBox.warning(self._mw, "AI", "No editor to apply the docstring.")
            return
        body = viewer.getText().strip()
        try:
            new_source = apply_google_docstring(editor.text or "", symbol, body)
        except ValueError as exc:
            QMessageBox.warning(self._mw, "AI", str(exc))
            return
        editor.setText(new_source)
        QMessageBox.information(self._mw, "AI", f"Docstring applied to {symbol}.")

    def _start(self, request: AiTaskRequest) -> None:
        self.ensureResultTab()
        self._mw.aiResultViewer.appendStatus(f"Starting: {request.title}")
        err = self._driver.start(request)
        if err:
            QMessageBox.information(self._mw, "AI", err)

    def _onProgress(self, message: str) -> None:
        viewer = getattr(self._mw, "aiResultViewer", None)
        if viewer is not None:
            viewer.appendStatus(message)

    def _onFinished(self, result) -> None:
        viewer = getattr(self._mw, "aiResultViewer", None)
        if viewer is None:
            return
        kind = getattr(result.kind, "value", str(result.kind))
        viewer.showResult(
            result.title,
            result.text,
            kind=kind,
            file_path=result.file_path,
            symbol_name=result.symbol_name,
            backend_name=result.backend_name,
        )
        self.ensureResultTab()

    def _onFailed(self, message: str) -> None:
        logging.error("AI task failed: %s", message)
        viewer = getattr(self._mw, "aiResultViewer", None)
        if viewer is not None:
            viewer.showResult("AI error", message, kind="error")
            self.ensureResultTab()
        else:
            QMessageBox.warning(self._mw, "AI error", message)
