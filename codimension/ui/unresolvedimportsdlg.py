# -*- coding: utf-8 -*-
#
# codimension - unresolved imports: exclude artifacts or install into venv
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Dialog: exclude build artifacts vs install unresolved packages into project venv."""

from __future__ import annotations

import logging
import os
from typing import Iterable

from ui.qt import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QRadioButton,
    Qt,
    QVBoxLayout,
)
from utils.analysis_excludes import (
    list_default_artifact_excludes,
    persist_artifact_excludes_to_project,
)
from utils.globals import GlobalData
from utils.pixmapcache import getIcon
from utils.unresolved_import_choice import (
    ACTION_EXCLUDE,
    ACTION_INSTALL,
    ACTION_SKIP,
    mark_unresolved_import_skipped,
    should_offer_unresolved_import_choice,
)
from utils.venvbootstrap import (
    MODE_SYNC,
    buildPipInstallCommand,
    requestAnalysisEnvironmentRefresh,
    requireMutableProjectPython,
)
from utils.venvprocess import ProcessCancelled, run_pip_with_progress

_LOG = logging.getLogger(__name__)


class UnresolvedImportsChoiceDialog(QDialog):
    """Mutually exclusive: exclude build artifacts, or pip-install packages."""

    def __init__(
        self,
        packages: list[str],
        parent=None,
        *,
        optional_packages: list[str] | None = None,
    ):
        QDialog.__init__(self, parent)
        self.setWindowTitle("Unresolved imports")
        self.setWindowIcon(getIcon("project.png"))
        self._packages = sorted({p for p in packages if p})
        self._optional = sorted({p for p in (optional_packages or []) if p})
        self._action = ACTION_SKIP
        self._selected: list[str] = []
        self._install_project = False
        self.__build()

    def __build(self) -> None:
        layout = QVBoxLayout(self)
        lines = ["Choose how to proceed:"]
        if self._packages:
            lines.insert(0, "Unresolved third-party imports (pip candidates):\n" + ", ".join(self._packages))
        if self._optional:
            lines.insert(
                0 if not self._packages else 1,
                "Optional imports (try/except ImportError — not PyPI packages):\n"
                + ", ".join(self._optional)
                + "\nDo not pip install these names; provide the local extension or Skip.",
            )
        layout.addWidget(QLabel("\n\n".join(lines), self))

        choice_box = QGroupBox("Action", self)
        choice_layout = QVBoxLayout(choice_box)
        self._exclude_radio = QRadioButton(
            "Exclude build artifacts (build/, dist/, .eggs, *.egg-info) from analysis",
            self,
        )
        self._install_radio = QRadioButton(
            "Install selected packages into the project venv",
            self,
        )
        self._exclude_radio.setChecked(True)
        if not self._packages:
            self._install_radio.setEnabled(False)
            self._install_radio.setToolTip(
                "No pip-installable unresolved packages; optional imports are not on PyPI."
            )
        group = QButtonGroup(self)
        group.addButton(self._exclude_radio)
        group.addButton(self._install_radio)
        choice_layout.addWidget(self._exclude_radio)
        choice_layout.addWidget(self._install_radio)
        layout.addWidget(choice_box)

        project = GlobalData().project
        artifacts = list_default_artifact_excludes(
            project.getProjectDir() if project.isLoaded() else None
        )
        if artifacts:
            layout.addWidget(
                QLabel(
                    "Detected artifact dirs:\n" + "\n".join(artifacts),
                    self,
                )
            )
        else:
            layout.addWidget(
                QLabel(
                    "No build/dist/.eggs/*.egg-info under the project root yet; "
                    "exclude still writes those names into excludeFromAnalysis when they appear.",
                    self,
                )
            )

        self._pkg_list = QListWidget(self)
        for name in self._packages:
            item = QListWidgetItem(name, self._pkg_list)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
        self._pkg_list.setEnabled(False)
        self._pkg_list.setVisible(bool(self._packages))
        layout.addWidget(QLabel("Packages for pip install:", self))
        layout.addWidget(self._pkg_list)

        project_dir = project.getProjectDir() if project.isLoaded() else ""
        has_pyproject = bool(
            project_dir and os.path.isfile(os.path.join(project_dir, "pyproject.toml"))
        )
        self._proj_check = QCheckBox("Also install project package (pip install .)", self)
        # Local accelerators like ``native`` are not shipped by haiduk-calib's pyproject.
        self._proj_check.setChecked(False)
        self._proj_check.setEnabled(False)
        self._proj_check.setVisible(has_pyproject)
        layout.addWidget(self._proj_check)

        self._exclude_radio.toggled.connect(self._on_mode)
        self._install_radio.toggled.connect(self._on_mode)
        self._on_mode()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.button(QDialogButtonBox.Ok).setText("Apply")
        buttons.button(QDialogButtonBox.Cancel).setText("Skip")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(560, 420)

    def _on_mode(self) -> None:
        install = self._install_radio.isChecked() and self._install_radio.isEnabled()
        self._pkg_list.setEnabled(install)
        self._proj_check.setEnabled(install and self._proj_check.isVisible())

    def _checked_packages(self) -> list[str]:
        names: list[str] = []
        for i in range(self._pkg_list.count()):
            item = self._pkg_list.item(i)
            if item.checkState() == Qt.Checked:
                names.append(item.text())
        return names

    def _on_accept(self) -> None:
        if self._exclude_radio.isChecked():
            self._action = ACTION_EXCLUDE
            self._selected = []
            self._install_project = False
            self.accept()
            return
        selected = self._checked_packages()
        install_proj = bool(self._proj_check.isChecked() and self._proj_check.isVisible())
        if not selected and not install_proj:
            QMessageBox.information(
                self,
                "Unresolved imports",
                "Select at least one package, or enable project install.",
            )
            return
        self._action = ACTION_INSTALL
        self._selected = selected
        self._install_project = install_proj
        self.accept()

    def result_action(self) -> tuple[str, list[str], bool]:
        """Return ``(action, packages, install_project)`` after exec."""
        if self.result() != QDialog.Accepted:
            return ACTION_SKIP, [], False
        return self._action, list(self._selected), self._install_project


def apply_unresolved_import_choice(
    project,
    action: str,
    packages: list[str] | None = None,
    *,
    install_project: bool = False,
    parent=None,
) -> bool:
    """Apply exclude or install choice. Returns True if something changed."""
    if project is None or not project.isLoaded():
        return False
    if action == ACTION_EXCLUDE:
        added = persist_artifact_excludes_to_project(project)
        try:
            from utils.settings import Settings

            Settings()["autoExcludeBuildArtifacts"] = True
        except Exception:
            pass
        if added:
            _LOG.info("Added to excludeFromAnalysis: %s", ", ".join(added))
        requestAnalysisEnvironmentRefresh(project)
        return True

    if action == ACTION_INSTALL:
        packages = [p for p in (packages or []) if p]
        if not packages and not install_project:
            return False
        python = requireMutableProjectPython(project)
        project_dir = project.getProjectDir()
        cmd = buildPipInstallCommand(
            python,
            mode=MODE_SYNC,
            packages=packages,
            install_project=install_project,
            project_dir=project_dir,
        )
        if len(cmd) <= 4:
            return False
        reply = QMessageBox.question(
            parent,
            "Confirm pip install",
            "Run:\n" + " ".join(cmd),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return False
        try:
            run_pip_with_progress(parent, cmd, cwd=project_dir, project_dir=project_dir)
        except RuntimeError as exc:
            detail = str(exc)
            if "No matching distribution found" in detail:
                raise RuntimeError(
                    detail
                    + "\n\nHint: optional/local modules (e.g. try/except ImportError) "
                    "are not on PyPI. Uncheck them, or install the project extension "
                    "that provides them — do not pip install the import name alone."
                ) from exc
            raise
        requestAnalysisEnvironmentRefresh(project)
        return True

    return False


def offer_unresolved_import_choice(
    parent,
    project,
    unresolved_packages: Iterable[str],
    *,
    optional_packages: Iterable[str] | None = None,
) -> str:
    """Show choice dialog when appropriate; apply result. Returns action taken."""
    packages = sorted({p for p in unresolved_packages if p})
    optional = sorted({p for p in (optional_packages or []) if p})
    combined = packages + optional
    if not should_offer_unresolved_import_choice(project, combined):
        return ACTION_SKIP

    from ui.qt import QApplication

    if QApplication.instance() is None:
        return ACTION_SKIP

    dlg = UnresolvedImportsChoiceDialog(packages, parent, optional_packages=optional)
    dlg.exec_()
    action, selected, install_proj = dlg.result_action()
    if action == ACTION_SKIP:
        mark_unresolved_import_skipped(project.getProjectDir(), combined)
        return ACTION_SKIP
    try:
        apply_unresolved_import_choice(
            project,
            action,
            selected,
            install_project=install_proj,
            parent=parent,
        )
    except ProcessCancelled:
        return ACTION_SKIP
    except Exception as exc:
        _LOG.exception("Unresolved import choice failed")
        QMessageBox.critical(parent, "Unresolved imports", str(exc))
        return ACTION_SKIP
    return action
