# -*- coding: utf-8 -*-
"""Non-blocking external process runner for VENV dialogs (audit A03 / R189).

GUI thread must not call ``subprocess.run`` for create/pip: long installs freeze
the IDE with no progress or cancel. This module runs argv via ``QProcess``,
pumps the Qt event loop, shows a cancelable progress dialog, and stops with
terminate → kill (same pattern as lint drivers).

R189: create runs at the **final** destination (backup/rollback), not via
staging rename that would bake wrong shebang paths.
"""

from __future__ import annotations

import os
import sys

from utils.venvbootstrap import (
    assertSafeMutableProjectPython,
    discardStagedVenv,
    moveAsideVenv,
    resolveVenvToPython,
    restoreVenvBackup,
    validateVenvDestination,
)

from .qt import QEventLoop, QProcess, QProgressDialog, Qt, QTimer

_STOP_KILL_TIMEOUT_MS = 2000


class ProcessCancelled(RuntimeError):
    """Raised when the user cancels the progress dialog."""


def run_argv_with_progress(
    parent,
    argv: list[str],
    *,
    cwd: str | None = None,
    title: str = "Working…",
    label: str = "",
) -> tuple[str, str]:
    """Run ``argv`` via ``QProcess`` while pumping the Qt event loop.

    Shows an indeterminate modal ``QProgressDialog`` with Cancel. Returns
    ``(stdout, stderr)``. Raises ``ProcessCancelled`` on cancel, ``RuntimeError``
    on start failure or non-zero exit.
    """
    if not argv:
        raise RuntimeError("empty command")

    process = QProcess(parent)
    process.setProcessChannelMode(QProcess.SeparateChannels)  # type: ignore[attr-defined]
    if cwd:
        process.setWorkingDirectory(cwd)

    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    cancelled = {"flag": False}
    stop_timer: QTimer | None = None
    loop = QEventLoop(parent)

    def _read_out() -> None:
        data = bytes(process.readAllStandardOutput())
        if data:
            stdout_chunks.append(data.decode("utf-8", errors="replace"))

    def _read_err() -> None:
        data = bytes(process.readAllStandardError())
        if data:
            stderr_chunks.append(data.decode("utf-8", errors="replace"))

    def _force_kill() -> None:
        if process.state() == QProcess.Running:  # type: ignore[attr-defined]
            process.kill()

    def _on_cancel() -> None:
        cancelled["flag"] = True
        if process.state() != QProcess.Running:  # type: ignore[attr-defined]
            loop.quit()
            return
        process.terminate()
        nonlocal stop_timer
        if stop_timer is not None:
            stop_timer.stop()
        stop_timer = QTimer(parent)
        stop_timer.setSingleShot(True)
        stop_timer.timeout.connect(_force_kill)
        stop_timer.start(_STOP_KILL_TIMEOUT_MS)

    process.readyReadStandardOutput.connect(_read_out)
    process.readyReadStandardError.connect(_read_err)
    process.finished.connect(loop.quit)

    progress = QProgressDialog(label or " ".join(argv[:8]), "Cancel", 0, 0, parent)
    progress.setWindowTitle(title)
    progress.setWindowModality(Qt.WindowModal)  # type: ignore[attr-defined]
    progress.setMinimumDuration(0)
    progress.setAutoClose(False)
    progress.setAutoReset(False)
    progress.canceled.connect(_on_cancel)
    progress.show()

    program, *args = argv
    process.start(program, args)
    if not process.waitForStarted(15000):
        progress.close()
        process.close()
        raise RuntimeError(f"process failed to start: {program}")

    loop.exec_()

    if stop_timer is not None:
        stop_timer.stop()

    _read_out()
    _read_err()
    # QProgressDialog::closeEvent calls cancel() unless the dialog is "finished".
    # Mark complete and block signals so close does not raise ProcessCancelled.
    progress.blockSignals(True)
    progress.setRange(0, 1)
    progress.setValue(1)
    progress.close()

    stdout = "".join(stdout_chunks)
    stderr = "".join(stderr_chunks)

    if cancelled["flag"]:
        raise ProcessCancelled("cancelled by user")

    if process.exitStatus() != QProcess.NormalExit or process.exitCode() != 0:  # type: ignore[attr-defined]
        detail = (stderr or stdout or f"exit {process.exitCode()}").strip()
        raise RuntimeError(f"command failed ({process.exitCode()}): {detail}")

    return stdout, stderr


def create_venv_in_place_with_progress(
    parent,
    base_python: str,
    venv_dir: str,
) -> str:
    """Create a venv at ``venv_dir`` via QProcess (no rename).

    Returns the new python path. Shebang/`VIRTUAL_ENV` use ``venv_dir``.
    """
    base_python = base_python or sys.executable
    venv_dir = os.path.abspath(venv_dir)
    if resolveVenvToPython(venv_dir):
        raise RuntimeError(f"venv already exists at {venv_dir}")
    os.makedirs(os.path.dirname(venv_dir) or ".", exist_ok=True)
    run_argv_with_progress(
        parent,
        [base_python, "-m", "venv", venv_dir],
        title="Creating venv",
        label=venv_dir,
    )
    python = resolveVenvToPython(venv_dir)
    if not python:
        raise RuntimeError(f"venv created but python not found under {venv_dir}")
    return str(python)


def create_venv_with_progress(
    parent,
    base_python: str,
    venv_dir: str,
    project_dir: str | None = None,
) -> str:
    """Create a venv via QProcess at the final path (R189).

    Applies :func:`validateVenvDestination` before starting. Creates in place
    so paths inside the venv match ``venv_dir``; on failure discards the
    half-written tree (and restores a backup when recreating over an existing
    destination that was moved aside — create path normally has no existing).
    """
    base_python = base_python or sys.executable
    venv_dir = validateVenvDestination(venv_dir, project_dir, for_recreate=False)
    backup = moveAsideVenv(venv_dir)
    try:
        create_venv_in_place_with_progress(parent, base_python, venv_dir)
        discardStagedVenv(backup)
        backup = None
    except Exception:
        discardStagedVenv(venv_dir)
        restoreVenvBackup(venv_dir, backup)
        raise
    python = resolveVenvToPython(venv_dir)
    if not python:
        raise RuntimeError(f"venv created but python not found under {venv_dir}")
    return str(python)


def run_pip_with_progress(
    parent,
    cmd: list[str],
    *,
    cwd: str | None = None,
    project_dir: str | None = None,
) -> None:
    """Run pip install via QProcess with progress/cancel; refuse IDE targets."""
    if cmd:
        assertSafeMutableProjectPython(cmd[0], project_dir=project_dir)
    run_argv_with_progress(
        parent,
        cmd,
        cwd=cwd,
        title="pip install",
        label=" ".join(cmd[:8]),
    )
