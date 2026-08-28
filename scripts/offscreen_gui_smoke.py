#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Headless production startup smoke (D07/B08/R197).

Creates CodimensionApplication + CodimensionMainWindow and loads plugins.
Exit 0 only when at least one bundled plugin activates.

R197 runs normal Python/Qt cleanup (``_shutdown_smoke``) before process exit.
A final ``os._exit(0)`` remains **after** that cleanup to avoid PyQt atexit
segfaults on some CI Python builds (historically rc=-11 after a successful
smoke). Failure paths return normally so traceback/atexit can run.
"""

from __future__ import annotations

import os
import sys
from typing import Any


def _ensure_imp_shim() -> None:
    """Install full ``imp`` compat for yapsy (load_module + PKG_DIRECTORY)."""
    try:
        from imp_compat import ensure_imp_compat
    except ImportError:
        from codimension.imp_compat import ensure_imp_compat  # type: ignore[no-redef]

    ensure_imp_compat()


def _ensure_wrapt_shim() -> None:
    """Restore ``inspect.formatargspec`` before any pylint/wrapt import (R197)."""
    try:
        from inspect_compat import ensure_wrapt_compat
    except ImportError:
        from codimension.inspect_compat import ensure_wrapt_compat  # type: ignore[no-redef]

    ensure_wrapt_compat()


def _shutdown_smoke(app: Any, main_window: Any) -> None:
    """Close the window, quit the app, and clear GlobalData (R197)."""
    from utils.globals import resetGlobalDataForTests

    try:
        if main_window is not None:
            main_window.close()
            if app is not None:
                app.processEvents()
    except Exception as exc:  # noqa: BLE001 — smoke must always finish teardown
        print(f"offscreen_gui_smoke: close warning: {exc}", file=sys.stderr)
    try:
        if app is not None:
            app.quit()
            app.processEvents()
    except Exception as exc:  # noqa: BLE001
        print(f"offscreen_gui_smoke: quit warning: {exc}", file=sys.stderr)
    resetGlobalDataForTests()


def main() -> int:
    """Bootstrap MainWindow + pluginManager.load(); require one active plugin."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    codim = os.path.join(root, "codimension")
    for path in (root, codim):
        if path not in sys.path:
            sys.path.insert(0, path)

    _ensure_wrapt_shim()
    _ensure_imp_shim()
    import parsers  # noqa: F401
    from utils.globals import GlobalData, resetGlobalDataForTests

    resetGlobalDataForTests()
    # Stable argv for CodimensionApplication (avoid ``-c`` / script-path quirks).
    sys.argv = [sys.argv[0] if sys.argv else "offscreen_gui_smoke.py"]

    saved_out, saved_err = sys.stdout, sys.stderr
    app = None
    main_window = None
    rc = 1
    try:
        # Local import path mirrors tests/debugger/ide_bootstrap.py
        from ui.application import CodimensionApplication
        from utils.settings import Settings
        from utils.skin import Skin, populateSampleSkin

        gd = GlobalData()
        gd.version = "smoke"
        settings = Settings()
        populateSampleSkin()
        skin = Skin()
        skin.loadByName(settings["skin"])
        gd.skin = skin
        os.environ["QT_X11_NO_NATIVE_MENUBAR"] = "1"
        app = CodimensionApplication(sys.argv, settings["style"])
        gd.application = app

        from ui.mainwindow import CodimensionMainWindow

        class FakeSplash:
            def showMessage(self, msg: str) -> None:
                del msg

        main_window = CodimensionMainWindow(FakeSplash(), settings)
        app.setMainWindow(main_window)
        gd.mainWindow = main_window

        sys.stdout, sys.stderr = saved_out, saved_err
        gd.pluginManager.load()
        active = sum(len(v) for v in gd.pluginManager.activePlugins.values())
        discovered = len(list(gd.pluginManager.getAllPlugins()))
        if discovered < 1 or active < 1:
            print(
                f"offscreen_gui_smoke: FAIL discovered={discovered} active={active}",
                file=sys.stderr,
            )
            return 1
        print(f"offscreen_gui_smoke: OK plugins_active={active} discovered={discovered}")
        sys.stdout.flush()
        sys.stderr.flush()
        rc = 0
        return 0
    finally:
        sys.stdout, sys.stderr = saved_out, saved_err
        _shutdown_smoke(app, main_window)
        if rc == 0:
            # Cleanup already ran; skip fragile PyQt interpreter shutdown.
            os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
