# -*- coding: utf-8 -*-
#
# codimension - SSH remote project open/create dialog
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Dialog to open or create a Codimension project over SSH/SFTP."""

from __future__ import annotations

import datetime
import os
import pwd
import socket
from typing import Callable, Optional

from utils.misc import getLocaleDate
from utils.ssh_remote import (
    RemoteProjectBinding,
    SshHostProfile,
    connect_paramiko_sftp,
    create_remote_project,
    default_cdm3_json,
    load_host_profiles,
    load_ssh_password,
    open_remote_project,
    remote_relpath,
    store_ssh_password,
    upsert_host_profile,
)

from .filedialogs import select_open_file
from .qt import (
    QApplication,
    QCheckBox,
    QComboBox,
    QCursor,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    Qt,
    QTextEdit,
    QVBoxLayout,
)
from .sshbrowse import SshBrowseDialog

ConnectFn = Callable[[SshHostProfile, str], object]


class SshRemoteProjectDialog(QDialog):
    """Collect host credentials and remote paths via SFTP browser, then open/create."""

    MODE_OPEN = "open"
    MODE_CREATE = "create"

    def __init__(
        self,
        parent=None,
        *,
        mode: str = MODE_OPEN,
        connect_fn: Optional[ConnectFn] = None,
        settings_dir: Optional[str] = None,
    ) -> None:
        QDialog.__init__(self, parent)
        self.__mode = mode if mode in (self.MODE_OPEN, self.MODE_CREATE) else self.MODE_OPEN
        self.__connect_fn = connect_fn
        self.__settings_dir = settings_dir
        self.__binding: Optional[RemoteProjectBinding] = None
        self.__profiles: list[SshHostProfile] = []
        self.__session = None

        title = "Open remote project (SSH)" if self.__mode == self.MODE_OPEN else "Create remote project (SSH)"
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(720, 640)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Remote-first: the project lives on the SSH host. "
                "Use Browse… to pick remote paths in a file-manager dialog "
                "(local cache: ~/.codimension3/remote-projects/).",
                self,
            )
        )

        layout.addWidget(self.__build_connection_group())
        layout.addWidget(self.__build_project_group())

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.__onAccept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.__reloadProfiles()
        self.__onAuthToggled()
        self.__fill_create_defaults()

    def binding(self) -> Optional[RemoteProjectBinding]:
        """Return the binding produced on successful accept."""
        return self.__binding

    def closeEvent(self, event) -> None:  # noqa: N802 — Qt API
        """Release the SFTP session when the dialog closes."""
        self.__close_session()
        QDialog.closeEvent(self, event)

    def reject(self) -> None:
        """Cancel and drop the session."""
        self.__close_session()
        QDialog.reject(self)

    def __build_connection_group(self) -> QGroupBox:
        box = QGroupBox("SSH connection", self)
        form = QFormLayout(box)

        self.__profileCombo = QComboBox(self)
        self.__profileCombo.currentIndexChanged.connect(self.__onProfileSelected)
        form.addRow("Saved host:", self.__profileCombo)

        self.__hostEdit = QLineEdit(self)
        self.__hostEdit.setPlaceholderText("hostname or IP")
        form.addRow("Host:", self.__hostEdit)

        self.__portSpin = QSpinBox(self)
        self.__portSpin.setRange(1, 65535)
        self.__portSpin.setValue(22)
        form.addRow("Port:", self.__portSpin)

        self.__userEdit = QLineEdit(self)
        form.addRow("User:", self.__userEdit)

        auth_row = QHBoxLayout()
        self.__authKeyRadio = QRadioButton("SSH key / agent", self)
        self.__authPassRadio = QRadioButton("Password", self)
        self.__authKeyRadio.setChecked(True)
        self.__authKeyRadio.toggled.connect(self.__onAuthToggled)
        auth_row.addWidget(self.__authKeyRadio)
        auth_row.addWidget(self.__authPassRadio)
        form.addRow("Auth:", auth_row)

        id_row = QHBoxLayout()
        self.__identityEdit = QLineEdit(self)
        self.__identityEdit.setPlaceholderText("~/.ssh/id_ed25519 (optional)")
        id_row.addWidget(self.__identityEdit)
        id_btn = QPushButton("...", self)
        id_btn.setToolTip("Choose local identity file")
        id_btn.clicked.connect(self.__browse_identity)
        id_row.addWidget(id_btn)
        form.addRow("Identity file:", id_row)

        self.__passwordEdit = QLineEdit(self)
        self.__passwordEdit.setEchoMode(QLineEdit.Password)
        form.addRow("Password:", self.__passwordEdit)

        self.__rememberPassCb = QCheckBox("Remember password (keyring or 0600 file)", self)
        form.addRow("", self.__rememberPassCb)

        self.__saveProfileCb = QCheckBox("Save host profile (no secrets in ssh_hosts.json)", self)
        self.__saveProfileCb.setChecked(True)
        form.addRow("", self.__saveProfileCb)

        conn_row = QHBoxLayout()
        self.__connectBtn = QPushButton("Connect…", self)
        self.__connectBtn.clicked.connect(self.__on_connect_clicked)
        self.__connStatus = QLabel("Not connected", self)
        conn_row.addWidget(self.__connectBtn)
        conn_row.addWidget(self.__connStatus, 1)
        form.addRow("", conn_row)
        return box

    def __build_project_group(self) -> QGroupBox:
        box = QGroupBox("Remote project", self)
        grid = QGridLayout(box)
        row = 0

        if self.__mode == self.MODE_OPEN:
            grid.addWidget(QLabel("Remote .cdm3 or project directory:", self), row, 0)
            self.__remotePathEdit = QLineEdit(self)
            self.__remotePathEdit.setPlaceholderText("Browse to select…")
            grid.addWidget(self.__remotePathEdit, row, 1)
            browse = QPushButton("Browse…", self)
            browse.clicked.connect(self.__browse_open_path)
            grid.addWidget(browse, row, 2)
            self.__projectNameEdit = QLineEdit(self)
            self.__projectNameEdit.hide()
            row += 1
        else:
            grid.addWidget(QLabel("Project name:", self), row, 0)
            self.__projectNameEdit = QLineEdit(self)
            self.__projectNameEdit.setPlaceholderText("project_name")
            grid.addWidget(self.__projectNameEdit, row, 1, 1, 2)
            row += 1

            grid.addWidget(QLabel("Parent directory (remote):", self), row, 0)
            self.__remotePathEdit = QLineEdit(self)
            self.__remotePathEdit.setPlaceholderText("Browse to select…")
            grid.addWidget(self.__remotePathEdit, row, 1)
            browse = QPushButton("Browse…", self)
            browse.clicked.connect(self.__browse_parent_dir)
            grid.addWidget(browse, row, 2)
            row += 1

            grid.addWidget(QLabel("Main script (remote):", self), row, 0)
            self.__scriptEdit = QLineEdit(self)
            grid.addWidget(self.__scriptEdit, row, 1)
            script_btn = QPushButton("Browse…", self)
            script_btn.clicked.connect(lambda: self.__browse_file_into(self.__scriptEdit, ["*.py"]))
            grid.addWidget(script_btn, row, 2)
            row += 1

            grid.addWidget(QLabel("Markdown doc (remote):", self), row, 0)
            self.__mdDocEdit = QLineEdit(self)
            grid.addWidget(self.__mdDocEdit, row, 1)
            md_btn = QPushButton("Browse…", self)
            md_btn.clicked.connect(lambda: self.__browse_file_into(self.__mdDocEdit, ["*.md"]))
            grid.addWidget(md_btn, row, 2)
            row += 1

            grid.addWidget(QLabel("Python interpreter / venv (remote):", self), row, 0)
            self.__venvEdit = QLineEdit(self)
            self.__venvEdit.setPlaceholderText("Optional remote python or venv path")
            grid.addWidget(self.__venvEdit, row, 1)
            venv_btn = QPushButton("Browse…", self)
            venv_btn.clicked.connect(self.__browse_venv)
            grid.addWidget(venv_btn, row, 2)
            row += 1

            grid.addWidget(QLabel("Version:", self), row, 0)
            self.__versionEdit = QLineEdit(self)
            grid.addWidget(self.__versionEdit, row, 1, 1, 2)
            row += 1

            grid.addWidget(QLabel("Author:", self), row, 0)
            self.__authorEdit = QLineEdit(self)
            grid.addWidget(self.__authorEdit, row, 1, 1, 2)
            row += 1

            grid.addWidget(QLabel("E-mail:", self), row, 0)
            self.__emailEdit = QLineEdit(self)
            grid.addWidget(self.__emailEdit, row, 1, 1, 2)
            row += 1

            grid.addWidget(QLabel("License:", self), row, 0)
            self.__licenseEdit = QLineEdit(self)
            grid.addWidget(self.__licenseEdit, row, 1, 1, 2)
            row += 1

            grid.addWidget(QLabel("Copyright:", self), row, 0)
            self.__copyrightEdit = QLineEdit(self)
            grid.addWidget(self.__copyrightEdit, row, 1, 1, 2)
            row += 1

            grid.addWidget(QLabel("Description:", self), row, 0)
            self.__descriptionEdit = QTextEdit(self)
            self.__descriptionEdit.setAcceptRichText(False)
            self.__descriptionEdit.setMaximumHeight(80)
            grid.addWidget(self.__descriptionEdit, row, 1, 1, 2)
            row += 1

            grid.addWidget(QLabel("Creation date:", self), row, 0)
            self.__creationDateEdit = QLineEdit(self)
            self.__creationDateEdit.setReadOnly(True)
            grid.addWidget(self.__creationDateEdit, row, 1, 1, 2)

        return box

    def __fill_create_defaults(self) -> None:
        if self.__mode != self.MODE_CREATE:
            return
        try:
            user_record = pwd.getpwuid(os.getuid())
            author = user_record[4].split(",")[0].strip() if user_record[4] else user_record[0]
            try:
                email = user_record[0] + "@" + socket.gethostname()
            except Exception:
                email = ""
        except Exception:
            author = ""
            email = ""
        self.__authorEdit.setText(author)
        self.__emailEdit.setText(email)
        self.__versionEdit.setText("0.0.1")
        self.__licenseEdit.setText("GPL v3")
        self.__copyrightEdit.setText(f"Copyright (c) {author}, {datetime.date.today().year}")
        self.__creationDateEdit.setText(getLocaleDate())
        self.__descriptionEdit.setPlainText("")

    def __reloadProfiles(self) -> None:
        self.__profiles = load_host_profiles(self.__settings_dir)
        self.__profileCombo.blockSignals(True)
        self.__profileCombo.clear()
        self.__profileCombo.addItem("(new)", None)
        for profile in self.__profiles:
            self.__profileCombo.addItem(profile.label or profile.id, profile.id)
        self.__profileCombo.blockSignals(False)

    def __onProfileSelected(self, _index: int = 0) -> None:
        profile_id = self.__profileCombo.currentData()
        if not profile_id:
            return
        for profile in self.__profiles:
            if profile.id != profile_id:
                continue
            self.__hostEdit.setText(profile.host)
            self.__portSpin.setValue(profile.port)
            self.__userEdit.setText(profile.user)
            if profile.auth == "password":
                self.__authPassRadio.setChecked(True)
            else:
                self.__authKeyRadio.setChecked(True)
            self.__identityEdit.setText(profile.identity_file)
            stored = load_ssh_password(profile.id, self.__settings_dir)
            if stored:
                self.__passwordEdit.setText(stored)
                self.__rememberPassCb.setChecked(True)
            break
        self.__onAuthToggled()
        self.__close_session()

    def __onAuthToggled(self, _checked: bool = False) -> None:
        use_password = self.__authPassRadio.isChecked()
        self.__passwordEdit.setEnabled(use_password)
        self.__rememberPassCb.setEnabled(use_password)
        self.__identityEdit.setEnabled(not use_password)

    def __browse_identity(self) -> None:
        path = select_open_file(
            self,
            "Select SSH identity file",
            os.path.expanduser("~/.ssh"),
            "All Files (*)",
        )
        if path:
            self.__identityEdit.setText(path)

    def __build_profile(self) -> SshHostProfile:
        existing_id = self.__profileCombo.currentData()
        return SshHostProfile(
            id=str(existing_id) if existing_id else "",
            host=self.__hostEdit.text().strip(),
            port=int(self.__portSpin.value()),
            user=self.__userEdit.text().strip(),
            auth="password" if self.__authPassRadio.isChecked() else "key",
            identity_file=self.__identityEdit.text().strip(),
            label="",
        ).normalized()

    def __password(self, profile: SshHostProfile) -> str:
        return self.__passwordEdit.text() if profile.auth == "password" else ""

    def __close_session(self) -> None:
        if self.__session is not None:
            try:
                self.__session.close()
            except Exception:
                pass
            self.__session = None
            self.__connStatus.setText("Not connected")

    def __ensure_session(self):
        """Connect (or reuse) an SFTP session for browsing."""
        if self.__session is not None:
            return self.__session
        try:
            profile = self.__build_profile()
        except ValueError as exc:
            QMessageBox.warning(self, self.windowTitle(), str(exc))
            return None
        password = self.__password(profile)
        if profile.auth == "password" and not password:
            QMessageBox.warning(self, self.windowTitle(), "Password is required for password auth.")
            return None
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        try:
            if self.__connect_fn is not None:
                self.__session = self.__connect_fn(profile, password)
            else:
                self.__session = connect_paramiko_sftp(profile, password=password)
        except Exception as exc:
            QMessageBox.warning(self, self.windowTitle(), f"SSH connect failed:\n{exc}")
            self.__session = None
            return None
        finally:
            QApplication.restoreOverrideCursor()
        self.__connStatus.setText(f"Connected: {profile.user + '@' if profile.user else ''}{profile.host}")
        if self.__saveProfileCb.isChecked():
            profile = upsert_host_profile(profile, self.__settings_dir)
            if profile.auth == "password" and self.__rememberPassCb.isChecked():
                store_ssh_password(profile.id, password, self.__settings_dir)
        return self.__session

    def __on_connect_clicked(self) -> None:
        self.__close_session()
        if self.__ensure_session() is not None:
            QMessageBox.information(self, self.windowTitle(), "Connected. Use Browse… to pick remote paths.")

    def __browse_open_path(self) -> None:
        session = self.__ensure_session()
        if session is None:
            return
        start = self.__remotePathEdit.text().strip() or "/"
        dlg = SshBrowseDialog(
            session,
            self,
            start_path=start,
            mode=SshBrowseDialog.MODE_FILE_OR_DIR,
            title="Select remote project (.cdm3 or directory)",
            name_filters=["*.cdm3"],
        )
        if dlg.exec_() == QDialog.Accepted and dlg.selected_path():
            self.__remotePathEdit.setText(dlg.selected_path())

    def __browse_parent_dir(self) -> None:
        session = self.__ensure_session()
        if session is None:
            return
        start = self.__remotePathEdit.text().strip() or "/"
        dlg = SshBrowseDialog(
            session,
            self,
            start_path=start,
            mode=SshBrowseDialog.MODE_DIR,
            title="Select remote parent directory",
        )
        if dlg.exec_() == QDialog.Accepted and dlg.selected_path():
            self.__remotePathEdit.setText(dlg.selected_path())

    def __browse_file_into(self, target: QLineEdit, filters: list[str]) -> None:
        session = self.__ensure_session()
        if session is None:
            return
        start = target.text().strip() or self.__remotePathEdit.text().strip() or "/"
        dlg = SshBrowseDialog(
            session,
            self,
            start_path=start,
            mode=SshBrowseDialog.MODE_FILE,
            title="Select remote file",
            name_filters=filters,
        )
        if dlg.exec_() == QDialog.Accepted and dlg.selected_path():
            target.setText(dlg.selected_path())

    def __browse_venv(self) -> None:
        session = self.__ensure_session()
        if session is None:
            return
        start = self.__venvEdit.text().strip() or self.__remotePathEdit.text().strip() or "/"
        # Prefer file (python binary); fall back to directory (venv root).
        dlg = SshBrowseDialog(
            session,
            self,
            start_path=start,
            mode=SshBrowseDialog.MODE_FILE_OR_DIR,
            title="Select remote Python interpreter or venv directory",
            name_filters=["python*", "*"],
        )
        if dlg.exec_() == QDialog.Accepted and dlg.selected_path():
            self.__venvEdit.setText(dlg.selected_path())

    def __build_create_cdm3(self, project_name: str, remote_root: str) -> str:
        script = self.__scriptEdit.text().strip()
        md_doc = self.__mdDocEdit.text().strip()
        venv = self.__venvEdit.text().strip()
        extra = {
            "scriptname": remote_relpath(remote_root, script) if script else "",
            "mddocfile": remote_relpath(remote_root, md_doc) if md_doc else "",
            "pythoninterpreter": remote_relpath(remote_root, venv) if venv else "",
            "author": self.__authorEdit.text().strip(),
            "email": self.__emailEdit.text().strip(),
            "license": self.__licenseEdit.text().strip(),
            "copyright": self.__copyrightEdit.text().strip(),
            "version": self.__versionEdit.text().strip(),
            "description": self.__descriptionEdit.toPlainText().strip(),
            "creationdate": self.__creationDateEdit.text().strip(),
            "importdirs": ["."],
        }
        return str(default_cdm3_json(project_name, extra))

    def __onAccept(self) -> None:
        try:
            profile = self.__build_profile()
        except ValueError as exc:
            QMessageBox.warning(self, self.windowTitle(), str(exc))
            return

        remote_path = self.__remotePathEdit.text().strip()
        if not remote_path:
            QMessageBox.warning(
                self,
                self.windowTitle(),
                "Remote path is required. Use Browse… after Connect.",
            )
            return

        project_name = self.__projectNameEdit.text().strip()
        if self.__mode == self.MODE_CREATE and not project_name:
            QMessageBox.warning(self, self.windowTitle(), "Project name is required.")
            return

        password = self.__password(profile)
        if profile.auth == "password" and not password:
            QMessageBox.warning(self, self.windowTitle(), "Password is required for password auth.")
            return

        if self.__saveProfileCb.isChecked():
            profile = upsert_host_profile(profile, self.__settings_dir)
        if profile.auth == "password" and self.__rememberPassCb.isChecked():
            store_ssh_password(profile.id, password, self.__settings_dir)

        session = self.__ensure_session()
        if session is None:
            return

        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        try:
            if self.__mode == self.MODE_OPEN:
                self.__binding = open_remote_project(session, profile, remote_path, settings_dir=self.__settings_dir)
            else:
                # New remote root = parent/name
                import posixpath

                remote_root = posixpath.normpath(posixpath.join(remote_path, project_name))
                if not remote_root.startswith("/"):
                    remote_root = "/" + remote_root
                body = self.__build_create_cdm3(project_name, remote_root)
                self.__binding = create_remote_project(
                    session,
                    profile,
                    remote_path,
                    project_name,
                    cdm3_body=body,
                    settings_dir=self.__settings_dir,
                )
        except Exception as exc:
            QMessageBox.warning(self, self.windowTitle(), f"SSH remote project failed:\n{exc}")
            return
        finally:
            QApplication.restoreOverrideCursor()
            self.__close_session()

        self.accept()
