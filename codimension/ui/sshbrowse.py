# -*- coding: utf-8 -*-
#
# codimension - remote SFTP path browser dialog
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Popup file/directory browser over an SFTP session (remote file manager)."""

from __future__ import annotations

import fnmatch
import posixpath
from typing import Optional

from .qt import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    Qt,
    QVBoxLayout,
)


class SshBrowseDialog(QDialog):
    """Navigate a remote filesystem and pick a file and/or directory."""

    MODE_DIR = "dir"
    MODE_FILE = "file"
    MODE_FILE_OR_DIR = "any"

    def __init__(
        self,
        session,
        parent=None,
        *,
        start_path: str = "/",
        mode: str = MODE_DIR,
        title: str = "Browse remote host",
        name_filters: Optional[list[str]] = None,
    ) -> None:
        QDialog.__init__(self, parent)
        self.__session = session
        self.__mode = mode if mode in (self.MODE_DIR, self.MODE_FILE, self.MODE_FILE_OR_DIR) else self.MODE_DIR
        self.__filters = list(name_filters or [])
        self.__cwd = "/"
        self.__selected = ""

        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(560, 420)

        layout = QVBoxLayout(self)
        path_row = QHBoxLayout()
        self.__upBtn = QPushButton("Up", self)
        self.__upBtn.clicked.connect(self.__go_up)
        path_row.addWidget(self.__upBtn)
        self.__pathEdit = QLineEdit(self)
        self.__pathEdit.setReadOnly(True)
        path_row.addWidget(self.__pathEdit)
        self.__goBtn = QPushButton("Go", self)
        self.__goBtn.clicked.connect(self.__go_typed)
        # Allow editing path then Go — unlock briefly via double-click of label hint
        self.__pathEdit.setReadOnly(False)
        path_row.addWidget(self.__goBtn)
        layout.addLayout(path_row)

        hint = {
            self.MODE_DIR: "Select a directory, then click Select.",
            self.MODE_FILE: "Open a directory, select a file, then click Select.",
            self.MODE_FILE_OR_DIR: "Select a .cdm3 file or a project directory, then click Select.",
        }.get(self.__mode, "")
        layout.addWidget(QLabel(hint, self))

        self.__list = QListWidget(self)
        self.__list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.__list.itemDoubleClicked.connect(self.__on_double_click)
        self.__list.itemSelectionChanged.connect(self.__on_selection_changed)
        layout.addWidget(self.__list)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        self.__okBtn = buttons.button(QDialogButtonBox.Ok)
        self.__okBtn.setText("Select")
        self.__okBtn.setEnabled(False)
        buttons.accepted.connect(self.__on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.__chdir(start_path or "/")

    def selected_path(self) -> str:
        """Return the chosen remote path after accept."""
        return self.__selected

    def __norm(self, path: str) -> str:
        text = (path or "").replace("\\", "/").strip() or "/"
        if not text.startswith("/"):
            text = "/" + text
        return posixpath.normpath(text)

    def __chdir(self, path: str) -> None:
        path = self.__norm(path)
        try:
            if not self.__session.isdir(path):
                raise FileNotFoundError(path)
            names = self.__session.listdir(path)
        except Exception as exc:
            QMessageBox.warning(self, self.windowTitle(), f"Cannot list {path}:\n{exc}")
            return
        self.__cwd = path
        self.__pathEdit.setText(path)
        self.__list.clear()
        self.__okBtn.setEnabled(self.__mode in (self.MODE_DIR, self.MODE_FILE_OR_DIR))

        entries: list[tuple[str, str, bool]] = []
        for name in names:
            if name in (".", ".."):
                continue
            full = self.__norm(posixpath.join(path, name))
            try:
                is_dir = self.__session.isdir(full)
            except Exception:
                continue
            if is_dir:
                entries.append((f"[dir]  {name}", full, True))
            else:
                if self.__filters and not any(fnmatch.fnmatch(name, pat) for pat in self.__filters):
                    if self.__mode == self.MODE_DIR:
                        continue
                    # Still hide non-matching files in file modes
                    continue
                if self.__mode == self.MODE_DIR:
                    continue
                entries.append((f"[file] {name}", full, False))

        entries.sort(key=lambda item: (not item[2], item[0].lower()))
        for label, full, is_dir in entries:
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, full)
            item.setData(Qt.UserRole + 1, is_dir)
            self.__list.addItem(item)

    def __go_up(self) -> None:
        parent = self.__norm(posixpath.dirname(self.__cwd) or "/")
        self.__chdir(parent)

    def __go_typed(self) -> None:
        self.__chdir(self.__pathEdit.text().strip() or "/")

    def __on_double_click(self, item: QListWidgetItem) -> None:
        full = item.data(Qt.UserRole)
        is_dir = bool(item.data(Qt.UserRole + 1))
        if is_dir:
            self.__chdir(str(full))
        elif self.__mode in (self.MODE_FILE, self.MODE_FILE_OR_DIR):
            self.__selected = str(full)
            self.accept()

    def __on_selection_changed(self) -> None:
        item = self.__list.currentItem()
        if item is None:
            self.__okBtn.setEnabled(self.__mode in (self.MODE_DIR, self.MODE_FILE_OR_DIR))
            return
        is_dir = bool(item.data(Qt.UserRole + 1))
        if self.__mode == self.MODE_DIR:
            self.__okBtn.setEnabled(True)
        elif self.__mode == self.MODE_FILE:
            self.__okBtn.setEnabled(not is_dir)
        else:
            self.__okBtn.setEnabled(True)

    def __on_accept(self) -> None:
        item = self.__list.currentItem()
        if item is not None:
            full = str(item.data(Qt.UserRole))
            is_dir = bool(item.data(Qt.UserRole + 1))
            if self.__mode == self.MODE_DIR:
                self.__selected = full if is_dir else self.__cwd
                self.accept()
                return
            if self.__mode == self.MODE_FILE:
                if is_dir:
                    QMessageBox.information(self, self.windowTitle(), "Please select a file.")
                    return
                self.__selected = full
                self.accept()
                return
            # FILE_OR_DIR
            self.__selected = full
            self.accept()
            return

        if self.__mode in (self.MODE_DIR, self.MODE_FILE_OR_DIR):
            self.__selected = self.__cwd
            self.accept()
            return
        QMessageBox.information(self, self.windowTitle(), "Please select a file.")
