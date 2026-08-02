# -*- coding: utf-8 -*-
"""Bootstrap CodimensionMainWindow for full-IDE offscreen smoke (T130)."""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ui.application import CodimensionApplication
    from ui.mainwindow import CodimensionMainWindow


class FakeSplash:
    """Stub splash — MainWindow only needs ``showMessage`` during construct."""

    def showMessage(self, msg: str) -> None:
        """No-op progress message (optional processEvents left to caller)."""
        del msg


def _configure_debugger_settings() -> object:
    """Inline stop-at-first-line settings (avoid qapp-bound fixtures)."""
    from utils.settings import DebuggerSettings, Settings

    settings = Settings()
    settings["floatingRenderer"] = False
    dbg = DebuggerSettings()
    dbg.stopAtFirstLine = True
    dbg.reportExceptions = True
    dbg.traceInterpreter = False
    settings.setDebuggerSettings(dbg)
    return settings


def build_main_window() -> tuple["CodimensionMainWindow", "CodimensionApplication"]:
    """Mirror ``codimension.py`` minimal UI bootstrap; return (window, app).

    Must not reuse a plain ``QApplication`` fixture — creates
    ``CodimensionApplication`` and assigns ``GlobalData().application``.
    """
    from ui.application import CodimensionApplication
    from utils.globals import GlobalData
    from utils.skin import Skin, populateSampleSkin

    os.environ["QT_X11_NO_NATIVE_MENUBAR"] = "1"

    gd = GlobalData()
    gd.version = "t130-smoke"
    settings = _configure_debugger_settings()
    populateSampleSkin()
    skin = Skin()
    skin.loadByName(settings["skin"])
    gd.skin = skin

    # CodimensionApplication must exist before importing MainWindow — several UI
    # modules instantiate QWidget subclasses at import time (e.g. MatchTooltip).
    app = CodimensionApplication(sys.argv, settings["style"])
    gd.application = app

    from ui.mainwindow import CodimensionMainWindow

    main_window = CodimensionMainWindow(FakeSplash(), settings)
    app.setMainWindow(main_window)
    gd.mainWindow = main_window
    return main_window, app
