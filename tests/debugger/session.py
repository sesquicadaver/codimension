# -*- coding: utf-8 -*-
"""Helpers to start/stop a CodimensionDebugger session without MainWindow."""

from __future__ import annotations

import logging
import sys
import time
import types
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from debugger.server import CodimensionDebugger
    from ui.qt import QApplication
    from utils.runmanager import RunManager

    from .host import DebuggerHost

_LOG = logging.getLogger(__name__)

# Collection-time imports need parser shims before utils.encoding pulls cdmpyparser.
_ROOT = Path(__file__).resolve().parents[2]
_CODIM = _ROOT / "codimension"
for _path in (str(_ROOT), str(_CODIM)):
    if _path not in sys.path:
        sys.path.insert(0, _path)


def write_script(directory: Path, name: str = "dbg_target.py", body: str | None = None) -> Path:
    """Write a small debuggee script and return its path."""
    if body is None:
        body = "x = 1\ny = 2\nz = x + y\nprint(z)\n"
    path = directory / name
    path.write_text(body, encoding="utf-8")
    return path.resolve()


def _install_fake_pick_widget(run_manager: "RunManager", host: "DebuggerHost") -> None:
    """Replace RunManager.__pickWidget so IOConsoleWidget/skin is never loaded."""
    from .host import FakeIOConsole

    def pick(self, procuuid, kind):
        widget = FakeIOConsole(procuuid, kind)
        host.addIOConsole(widget, kind)
        return widget

    run_manager._RunManager__pickWidget = types.MethodType(pick, run_manager)


def build_session(qapp: "QApplication") -> tuple[object, "RunManager", "CodimensionDebugger"]:
    """Wire mixin host + RunManager + CodimensionDebugger like MainWindow does."""
    del qapp  # ensure caller created QApplication first
    import parsers  # noqa: F401
    from debugger.server import CodimensionDebugger
    from utils.runmanager import RunManager

    from .host import create_mixin_host

    host = create_mixin_host()
    debugger = CodimensionDebugger(host)
    host._debugger = debugger
    run_manager = RunManager(host)
    host._runManager = run_manager
    _install_fake_pick_widget(run_manager, host)
    run_manager.sigDebugSessionPrologueStarted.connect(debugger.onDebugSessionStarted)
    run_manager.sigIncomingMessage.connect(debugger.onIncomingMessage)
    run_manager.sigProcessFinished.connect(debugger.onProcessFinished)
    return host, run_manager, debugger


def wait_until(
    predicate: Callable[[], bool],
    qapp: "QApplication",
    timeout_s: float = 15.0,
    poll_s: float = 0.05,
) -> bool:
    """Pump Qt events until predicate() is true or timeout."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(poll_s)
    qapp.processEvents()
    return predicate()


def wait_state(
    debugger: "CodimensionDebugger",
    state: int,
    qapp: "QApplication",
    timeout_s: float = 15.0,
) -> bool:
    """Wait until debugger.getState() equals ``state``."""
    return wait_until(lambda: debugger.getState() == state, qapp, timeout_s=timeout_s)


def teardown_session(
    debugger: "CodimensionDebugger",
    run_manager: "RunManager",
    qapp: "QApplication",
) -> None:
    """Stop debugging and kill any leftover redirected processes."""
    from debugger.server import CodimensionDebugger as _Dbg

    try:
        if debugger.getState() != _Dbg.STATE_STOPPED:
            debugger.stopDebugging()
            wait_state(debugger, _Dbg.STATE_STOPPED, qapp, timeout_s=5.0)
    except Exception:
        _LOG.exception("teardown: stopDebugging failed")
    try:
        remaining = getattr(run_manager, "_RunManager__processes", [])
        if remaining:
            run_manager.killAll()
        wait_until(lambda: debugger.getState() == _Dbg.STATE_STOPPED, qapp, timeout_s=3.0)
    except Exception:
        _LOG.exception("teardown: killAll failed")
    qapp.processEvents()
