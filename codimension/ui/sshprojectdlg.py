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

from typing import Callable, Optional

from utils.ssh_remote import (
    RemoteProjectBinding,
    SshHostProfile,
    connect_paramiko_sftp,
    create_remote_project,
    default_cdm3_json,
    load_host_profiles,
    load_ssh_password,
    open_remote_project,
    store_ssh_password,
    upsert_host_profile,
)

from .qt import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
)

ConnectFn = Callable[[SshHostProfile, str], object]


class SshRemoteProjectDialog(QDialog):
    """Collect host credentials and remote path, then open/create via SFTP."""

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

        title = "Open remote project (SSH)" if self.__mode == self.MODE_OPEN else "New remote project (SSH)"
        self.setWindowTitle(title)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Remote-first: the project lives on the SSH host; "
                "Codimension downloads a local cache under ~/.codimension3/remote-projects/.",
                self,
            )
        )

        form = QFormLayout()
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

        self.__identityEdit = QLineEdit(self)
        self.__identityEdit.setPlaceholderText("~/.ssh/id_ed25519 (optional)")
        form.addRow("Identity file:", self.__identityEdit)

        self.__passwordEdit = QLineEdit(self)
        self.__passwordEdit.setEchoMode(QLineEdit.Password)
        form.addRow("Password:", self.__passwordEdit)

        self.__rememberPassCb = QCheckBox("Remember password (keyring or 0600 file)", self)
        form.addRow("", self.__rememberPassCb)

        self.__saveProfileCb = QCheckBox("Save host profile (no secrets in ssh_hosts.json)", self)
        self.__saveProfileCb.setChecked(True)
        form.addRow("", self.__saveProfileCb)

        path_hint = (
            "Remote .cdm3 file or directory containing one"
            if self.__mode == self.MODE_OPEN
            else "Remote parent directory for the new project"
        )
        self.__remotePathEdit = QLineEdit(self)
        self.__remotePathEdit.setPlaceholderText(path_hint)
        form.addRow("Remote path:", self.__remotePathEdit)

        self.__projectNameEdit = QLineEdit(self)
        self.__projectNameEdit.setPlaceholderText("project_name")
        if self.__mode == self.MODE_CREATE:
            form.addRow("Project name:", self.__projectNameEdit)
        else:
            self.__projectNameEdit.hide()

        layout.addLayout(form)

        hint = QLabel(
            "Requires optional dependency: pip install 'paramiko>=3.0' (or pip install -e '.[ssh]').",
            self,
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.__onAccept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.__reloadProfiles()
        self.__onAuthToggled()

    def binding(self) -> Optional[RemoteProjectBinding]:
        """Return the binding produced on successful accept."""
        return self.__binding

    def __reloadProfiles(self) -> None:
        """Load saved profiles into the combo."""
        self.__profiles = load_host_profiles(self.__settings_dir)
        self.__profileCombo.blockSignals(True)
        self.__profileCombo.clear()
        self.__profileCombo.addItem("(new)", None)
        for profile in self.__profiles:
            self.__profileCombo.addItem(profile.label or profile.id, profile.id)
        self.__profileCombo.blockSignals(False)

    def __onProfileSelected(self, _index: int = 0) -> None:
        """Fill connection fields from the selected saved profile."""
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

    def __onAuthToggled(self, _checked: bool = False) -> None:
        """Enable password vs identity controls."""
        use_password = self.__authPassRadio.isChecked()
        self.__passwordEdit.setEnabled(use_password)
        self.__rememberPassCb.setEnabled(use_password)
        self.__identityEdit.setEnabled(not use_password)

    def __build_profile(self) -> SshHostProfile:
        """Build a normalized profile from the form."""
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

    def __onAccept(self) -> None:
        """Validate, connect, open/create, then accept the dialog."""
        try:
            profile = self.__build_profile()
        except ValueError as exc:
            QMessageBox.warning(self, self.windowTitle(), str(exc))
            return

        remote_path = self.__remotePathEdit.text().strip()
        if not remote_path:
            QMessageBox.warning(self, self.windowTitle(), "Remote path is required.")
            return

        project_name = self.__projectNameEdit.text().strip()
        if self.__mode == self.MODE_CREATE and not project_name:
            QMessageBox.warning(self, self.windowTitle(), "Project name is required.")
            return

        password = self.__passwordEdit.text() if profile.auth == "password" else ""
        if profile.auth == "password" and not password:
            QMessageBox.warning(self, self.windowTitle(), "Password is required for password auth.")
            return

        if self.__saveProfileCb.isChecked():
            profile = upsert_host_profile(profile, self.__settings_dir)

        if profile.auth == "password" and self.__rememberPassCb.isChecked():
            store_ssh_password(profile.id, password, self.__settings_dir)

        session = None
        try:
            if self.__connect_fn is not None:
                session = self.__connect_fn(profile, password)
            else:
                session = connect_paramiko_sftp(profile, password=password)
            if self.__mode == self.MODE_OPEN:
                self.__binding = open_remote_project(session, profile, remote_path, settings_dir=self.__settings_dir)
            else:
                self.__binding = create_remote_project(
                    session,
                    profile,
                    remote_path,
                    project_name,
                    cdm3_body=default_cdm3_json(project_name),
                    settings_dir=self.__settings_dir,
                )
        except Exception as exc:
            QMessageBox.warning(self, self.windowTitle(), f"SSH remote project failed:\n{exc}")
            return
        finally:
            if session is not None:
                try:
                    session.close()
                except Exception:
                    pass

        self.accept()
