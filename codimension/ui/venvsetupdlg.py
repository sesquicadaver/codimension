# -*- coding: utf-8 -*-
"""Dialogs for project VENV setup / update (T140 / T141)."""

from __future__ import annotations

import logging
import os
import sys

from utils.globals import GlobalData
from utils.pixmapcache import getIcon
from utils.venvbootstrap import (
    MODE_RECREATE,
    MODE_SYNC,
    MODE_UPGRADE,
    bindInterpreter,
    buildPipInstallCommand,
    collectInstallSources,
    discoverRootVenvCandidates,
    getEffectiveProjectPython,
    isPathInsideProject,
    recreateVenv,
    requestAnalysisEnvironmentRefresh,
    requireMutableProjectPython,
    selectedUnresolvedPackages,
    venvDirFromPython,
)
from utils.venvutils import resolveVenvToPython

from .qt import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    Qt,
    QVBoxLayout,
)
from .venvprocess import (
    ProcessCancelled,
    create_venv_with_progress,
    run_pip_with_progress,
)

_LOG = logging.getLogger(__name__)


def _add_sources_widgets(parent, layout, project):
    """Add install-source widgets.

    Returns ``(req_checks, pyproject_cb, unresolved_cb, pkg_list)``.
    Unresolved packages are opt-in (unchecked by default) with a multi-select
    review list (T141).
    """
    sources = collectInstallSources(project)
    layout.addWidget(QLabel("Select sources, then confirm pip install.", parent))
    req_checks = []
    for path in sources["requirement_files"]:
        cb = QCheckBox(os.path.basename(path), parent)
        cb.setChecked(True)
        cb.setProperty("req_path", path)
        req_checks.append(cb)
        layout.addWidget(cb)
    pyproject_cb = QCheckBox("pyproject.toml → pip install .", parent)
    pyproject_cb.setEnabled(sources["has_pyproject"])
    pyproject_cb.setChecked(sources["has_pyproject"])
    layout.addWidget(pyproject_cb)

    packages = list(sources["unresolved_packages"])
    summary = ", ".join(packages[:8]) if packages else "none"
    unresolved_cb = QCheckBox(f"Unresolved packages ({summary})", parent)
    unresolved_cb.setEnabled(bool(packages))
    unresolved_cb.setChecked(False)
    layout.addWidget(unresolved_cb)

    pkg_list = QListWidget(parent)
    pkg_list.setMaximumHeight(120)
    for pkg in packages:
        item = QListWidgetItem(pkg)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)
        pkg_list.addItem(item)
    pkg_list.setEnabled(False)
    pkg_list.setVisible(bool(packages))
    unresolved_cb.toggled.connect(pkg_list.setEnabled)
    layout.addWidget(pkg_list)
    if packages:
        layout.addWidget(QLabel("Enable unresolved, then review the checked packages above.", parent))
    return req_checks, pyproject_cb, unresolved_cb, pkg_list


def _packages_from_list(pkg_list):
    """Return ``[(name, checked), …]`` from a QListWidget of checkable items."""
    items = []
    for index in range(pkg_list.count()):
        item = pkg_list.item(index)
        items.append((item.text(), item.checkState() == Qt.Checked))
    return items


def _selected_sources(req_checks, pyproject_cb, unresolved_cb, pkg_list):
    """Return (requirement_files, packages, install_project)."""
    reqs = [cb.property("req_path") for cb in req_checks if cb.isChecked()]
    pkgs = selectedUnresolvedPackages(unresolved_cb.isChecked(), _packages_from_list(pkg_list))
    return reqs, pkgs, pyproject_cb.isChecked()


def selectedBaseInterpreter(combo: QComboBox, *, fallback: str | None = None) -> str:
    """Resolve base Python from an editable combo (audit D01 @ 8c60ad5c).

    ``QComboBox.setEditText`` does not clear ``currentIndex``, so
    ``currentData()`` alone keeps returning the default item's path after Browse
    or manual edits. Prefer ``currentText`` when it differs from the selected
    item label; use item data only when the visible text still matches that item.
    """
    fallback = fallback or sys.executable
    text = (combo.currentText() or "").strip()
    data = combo.currentData()
    if not text:
        return str(data) if data else fallback
    idx = combo.currentIndex()
    if idx >= 0 and text == combo.itemText(idx):
        return str(data) if data else fallback
    return text


class VenvSetupDialog(QDialog):
    """Create or attach a project venv, then optionally install dependencies."""

    def __init__(self, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowTitle("Project VENV")
        self.setWindowIcon(getIcon("project.png"))
        self._project = GlobalData().project
        self._project_dir = self._project.getProjectDir()
        self.__build()

    def __build(self):
        layout = QVBoxLayout(self)

        attach_box = QGroupBox("Existing venv in project root", self)
        attach_layout = QVBoxLayout(attach_box)
        self._candidate_list = QListWidget(self)
        self._candidate_list.addItem(QListWidgetItem("(ignore — create new)"))
        candidates = discoverRootVenvCandidates(self._project_dir)
        for path in candidates:
            self._candidate_list.addItem(QListWidgetItem(path))
        # Prefer attach when a root venv already exists (audit P0 @ 9df7eca7)
        self._candidate_list.setCurrentRow(1 if candidates else 0)
        attach_layout.addWidget(self._candidate_list)
        layout.addWidget(attach_box)

        create_box = QGroupBox("Create new venv", self)
        create_layout = QVBoxLayout(create_box)
        row = QHBoxLayout()
        row.addWidget(QLabel("Location:", self))
        self._location_edit = QLineEdit(os.path.join(self._project_dir, ".venv"), self)
        row.addWidget(self._location_edit)
        browse = QPushButton("…", self)
        browse.clicked.connect(self._browse_location)
        row.addWidget(browse)
        create_layout.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Base interpreter:", self))
        self._base_combo = QComboBox(self)
        self._base_combo.setEditable(True)
        self._base_combo.addItem(f"System default ({sys.executable})", sys.executable)
        row2.addWidget(self._base_combo)
        pick_py = QPushButton("Browse…", self)
        pick_py.clicked.connect(self._browse_base_python)
        row2.addWidget(pick_py)
        create_layout.addLayout(row2)
        layout.addWidget(create_box)

        sources_box = QGroupBox("Install sources (optional)", self)
        sources_layout = QVBoxLayout(sources_box)
        (
            self._req_checks,
            self._pyproject_check,
            self._unresolved_check,
            self._pkg_list,
        ) = _add_sources_widgets(self, sources_layout, self._project)
        layout.addWidget(sources_box)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(560, 480)

    def _browse_location(self):
        path = QFileDialog.getExistingDirectory(self, "Venv parent directory", self._project_dir)
        if path:
            self._location_edit.setText(os.path.join(path, ".venv"))

    def _browse_base_python(self):
        path, _ = QFileDialog.getOpenFileName(self, "Base Python interpreter", "/usr/bin", "All (*)")
        if path:
            # Clear item selection so currentData() cannot shadow the browsed path.
            self._base_combo.setCurrentIndex(-1)
            self._base_combo.setEditText(path)

    def _on_accept(self):
        try:
            row = self._candidate_list.currentRow()
            if row > 0:
                venv_dir = self._candidate_list.currentItem().text()
                python = resolveVenvToPython(venv_dir)
                if not python:
                    QMessageBox.warning(self, "VENV", "Selected venv has no usable python.")
                    return
            else:
                location = self._location_edit.text().strip()
                if not location:
                    QMessageBox.warning(self, "VENV", "Choose a venv location.")
                    return
                base = selectedBaseInterpreter(self._base_combo)
                python = create_venv_with_progress(self, base, location, project_dir=self._project_dir)

            reqs, packages, install_proj = _selected_sources(
                self._req_checks,
                self._pyproject_check,
                self._unresolved_check,
                self._pkg_list,
            )
            if reqs or packages or install_proj:
                from utils.venvbootstrap import assertSafeMutableProjectPython

                assertSafeMutableProjectPython(python)
                cmd = buildPipInstallCommand(
                    python,
                    mode=MODE_SYNC,
                    requirement_files=reqs,
                    packages=packages,
                    install_project=install_proj,
                    project_dir=self._project_dir,
                )
                reply = QMessageBox.question(
                    self,
                    "Confirm pip install",
                    "Run:\n" + " ".join(cmd),
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if reply == QMessageBox.Yes:
                    run_pip_with_progress(self, cmd, cwd=self._project_dir)

            persist = (
                QMessageBox.question(
                    self,
                    "Save interpreter",
                    "Save this venv path into project settings (pythoninterpreter)?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes,
                )
                == QMessageBox.Yes
            )
            bindInterpreter(self._project, python, persist=persist)
            requestAnalysisEnvironmentRefresh(self._project)
            self.accept()
        except ProcessCancelled:
            return
        except Exception as exc:
            _LOG.exception("VENV setup failed")
            QMessageBox.critical(self, "VENV", str(exc))


class VenvUpdateDialog(QDialog):
    """Update packages in the effective project venv (upgrade/sync/recreate)."""

    def __init__(self, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowTitle("Update VENV")
        self.setWindowIcon(getIcon("project.png"))
        self._project = GlobalData().project
        self._project_dir = self._project.getProjectDir()
        try:
            self._python = requireMutableProjectPython(self._project)
        except RuntimeError as exc:
            QMessageBox.warning(self, "Update VENV", str(exc))
            # Still build UI with effective path for display; accept will re-check.
            self._python = getEffectiveProjectPython(self._project)
            self._mutable_blocked = str(exc)
        else:
            self._mutable_blocked = ""
        self.__build()

    def __build(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Target interpreter:\n{self._python}", self))

        mode_box = QGroupBox("Update mode", self)
        mode_layout = QVBoxLayout(mode_box)
        self._sync_radio = QRadioButton("Sync — install missing (no --upgrade)", self)
        self._upgrade_radio = QRadioButton("Upgrade — pip install --upgrade", self)
        self._recreate_radio = QRadioButton("Recreate — delete venv, create, sync install", self)
        self._sync_radio.setChecked(True)
        mode_layout.addWidget(self._sync_radio)
        mode_layout.addWidget(self._upgrade_radio)
        mode_layout.addWidget(self._recreate_radio)
        layout.addWidget(mode_box)

        sources_box = QGroupBox("Install sources", self)
        sources_layout = QVBoxLayout(sources_box)
        (
            self._req_checks,
            self._pyproject_check,
            self._unresolved_check,
            self._pkg_list,
        ) = _add_sources_widgets(self, sources_layout, self._project)
        layout.addWidget(sources_box)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(560, 460)

    def _mode(self):
        if self._upgrade_radio.isChecked():
            return MODE_UPGRADE
        if self._recreate_radio.isChecked():
            return MODE_RECREATE
        return MODE_SYNC

    def _on_accept(self):
        if self._mutable_blocked:
            QMessageBox.warning(self, "Update VENV", self._mutable_blocked)
            return
        try:
            self._python = requireMutableProjectPython(self._project)
        except RuntimeError as exc:
            QMessageBox.warning(self, "Update VENV", str(exc))
            return
        mode = self._mode()
        reqs, packages, install_proj = _selected_sources(
            self._req_checks,
            self._pyproject_check,
            self._unresolved_check,
            self._pkg_list,
        )
        try:
            if mode == MODE_RECREATE:
                venv_dir = venvDirFromPython(self._python)
                if not venv_dir:
                    QMessageBox.warning(self, "Update VENV", "Cannot determine venv directory from interpreter.")
                    return
                if not isPathInsideProject(venv_dir, self._project_dir):
                    QMessageBox.warning(self, "Update VENV", "Recreate refused: venv is outside the project.")
                    return
                reply = QMessageBox.warning(
                    self,
                    "Confirm recreate",
                    f"Delete and recreate:\n{venv_dir}\n\nThis cannot be undone.",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if reply != QMessageBox.Yes:
                    return
                python = recreateVenv(
                    sys.executable,
                    venv_dir,
                    self._project_dir,
                    requirement_files=reqs,
                    packages=packages,
                    install_project=install_proj,
                    runner_create=lambda base, path: create_venv_with_progress(
                        self, base, path, project_dir=self._project_dir
                    ),
                    runner_pip=lambda cmd, cwd=None: run_pip_with_progress(self, cmd, cwd=cwd),
                )
                persist = bool(self._project.props.get("pythoninterpreter", "").strip())
                bindInterpreter(self._project, python, persist=persist)
            else:
                cmd = buildPipInstallCommand(
                    self._python,
                    mode=mode,
                    requirement_files=reqs,
                    packages=packages,
                    install_project=install_proj,
                    project_dir=self._project_dir,
                )
                if len(cmd) <= 4:
                    QMessageBox.information(self, "Update VENV", "No install sources selected.")
                    return
                reply = QMessageBox.question(
                    self,
                    "Confirm pip install",
                    "Run:\n" + " ".join(cmd),
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if reply != QMessageBox.Yes:
                    return
                run_pip_with_progress(self, cmd, cwd=self._project_dir)
            requestAnalysisEnvironmentRefresh(self._project)
            self.accept()
        except ProcessCancelled:
            return
        except Exception as exc:
            _LOG.exception("Update VENV failed")
            QMessageBox.critical(self, "Update VENV", str(exc))
