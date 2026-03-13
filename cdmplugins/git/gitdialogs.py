# -*- coding: utf-8 -*-
#
# Codimension - Python 3 experimental IDE
# Copyright (C) 2025  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Git plugin dialogs: Commit, Create branch, Create PR, Repo override."""

from ui.qt import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)


class CommitDialog(QDialog):
    """Dialog for commit message and options."""

    def __init__(self, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowTitle("Git Commit")

        layout = QVBoxLayout(self)
        grid = QGridLayout()
        grid.addWidget(QLabel("Message:", self), 0, 0)
        self.__messageEdit = QLineEdit(self)
        self.__messageEdit.setPlaceholderText("Commit message")
        grid.addWidget(self.__messageEdit, 0, 1)
        layout.addLayout(grid)

        self.__amendCb = QCheckBox("Amend previous commit", self)
        layout.addWidget(self.__amendCb)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_message(self):
        """Return the commit message."""
        return self.__messageEdit.text()

    def get_amend(self):
        """Return whether amend is checked."""
        return self.__amendCb.isChecked()


class SelectBranchDialog(QDialog):
    """Dialog to select a branch to switch to (checkout)."""

    def __init__(self, git_root, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowTitle("Git — Switch Branch")
        self.__gitRoot = git_root

        try:
            from .gitdriver import get_current_branch, list_branches

            branches = list_branches(git_root, include_remote=True)
            current = get_current_branch(git_root)
        except ImportError:
            branches = []
            current = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select branch:", self))
        self.__listWidget = QListWidget(self)
        self.__listWidget.setMinimumHeight(200)
        for name, is_curr in branches:
            item = QListWidgetItem(("✓ " if is_curr else "  ") + name)
            item.setData(256, name)
            self.__listWidget.addItem(item)
            if is_curr:
                self.__listWidget.setCurrentItem(item)
        if branches and not self.__listWidget.currentItem():
            self.__listWidget.setCurrentRow(0)
        layout.addWidget(self.__listWidget)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_selected_branch(self):
        """Return selected branch name or None."""
        item = self.__listWidget.currentItem()
        if item is None:
            return None
        return item.data(256)


class CreateBranchDialog(QDialog):
    """Dialog for creating a new branch."""

    def __init__(self, git_root, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowTitle("Git Create Branch")
        self.__gitRoot = git_root

        layout = QVBoxLayout(self)
        grid = QGridLayout()
        grid.addWidget(QLabel("Branch name:", self), 0, 0)
        self.__nameEdit = QLineEdit(self)
        self.__nameEdit.setPlaceholderText("feature/my-branch")
        grid.addWidget(self.__nameEdit, 0, 1)
        layout.addLayout(grid)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_branch_name(self):
        """Return the branch name."""
        return self.__nameEdit.text()


class CreatePRDialog(QDialog):
    """Dialog for creating a pull request."""

    def __init__(self, git_root, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowTitle("Create Pull Request")
        self.__gitRoot = git_root

        layout = QVBoxLayout(self)
        grid = QGridLayout()

        self.__baseEdit = QLineEdit(self)
        self.__baseEdit.setPlaceholderText("main")
        self.__baseEdit.setText("main")
        grid.addWidget(QLabel("Base branch:", self), 0, 0)
        grid.addWidget(self.__baseEdit, 0, 1)

        self.__titleEdit = QLineEdit(self)
        self.__titleEdit.setPlaceholderText("PR title")
        grid.addWidget(QLabel("Title:", self), 1, 0)
        grid.addWidget(self.__titleEdit, 1, 1)

        self.__bodyEdit = QTextEdit(self)
        self.__bodyEdit.setPlaceholderText("Description (optional)")
        self.__bodyEdit.setMaximumHeight(120)
        grid.addWidget(QLabel("Body:", self), 2, 0)
        grid.addWidget(self.__bodyEdit, 2, 1)

        layout.addLayout(grid)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_values(self):
        """Return (base_branch, title, body)."""
        return (
            self.__baseEdit.text().strip(),
            self.__titleEdit.text().strip(),
            self.__bodyEdit.toPlainText().strip(),
        )


class RepoOverrideDialog(QDialog):
    """Dialog to set GitHub repository and clone to open project."""

    def __init__(self, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowTitle("Git — Repository")

        try:
            from .gitconfig import get_github_repo_override

            current = get_github_repo_override()
        except ImportError:
            current = ""

        layout = QVBoxLayout(self)
        grid = QGridLayout()
        self.__repoEdit = QLineEdit(self)
        self.__repoEdit.setPlaceholderText("owner/repo or https://github.com/owner/repo")
        self.__repoEdit.setText(current)
        grid.addWidget(QLabel("Repository:", self), 0, 0)
        grid.addWidget(self.__repoEdit, 0, 1)

        self.__cloneToEdit = QLineEdit(self)
        self.__cloneToEdit.setPlaceholderText("Full path, e.g. ~/Projects/repo_name")
        self.__cloneToEdit.setText(self._default_clone_dir(current))
        grid.addWidget(QLabel("Clone to:", self), 1, 0)
        grid.addWidget(self.__cloneToEdit, 1, 1)
        browseBtn = QPushButton("Browse...", self)
        browseBtn.clicked.connect(self._on_browse)
        grid.addWidget(browseBtn, 1, 2)

        self.__openAfterCb = QCheckBox("Open project after clone", self)
        self.__openAfterCb.setChecked(True)
        layout.addLayout(grid)
        layout.addWidget(self.__openAfterCb)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _default_clone_dir(self, repo_spec: str) -> str:
        """Default clone directory: ~/Projects/repo_name."""
        import os

        try:
            from .gitdriver import repo_spec_to_clone_url

            url = repo_spec_to_clone_url(repo_spec)
            repo_name = url.rstrip("/").rstrip(".git").split("/")[-1] if url else "repo"
        except Exception:
            repo_name = "repo"
        base = os.path.expanduser("~/Projects")
        return os.path.join(base, repo_name)

    def _on_browse(self):
        """Browse for parent directory. Repo will be cloned as subfolder parent/repo_name."""
        import os

        path = QFileDialog.getExistingDirectory(
            self, "Select parent directory (repo will be cloned as subfolder)"
        )
        if path:
            repo_spec = self.__repoEdit.text().strip()
            try:
                from .gitdriver import repo_spec_to_clone_url

                url = repo_spec_to_clone_url(repo_spec)
                repo_name = url.rstrip("/").rstrip(".git").split("/")[-1] if url else "repo"
            except Exception:
                repo_name = "repo"
            full_path = os.path.join(path, repo_name)
            self.__cloneToEdit.setText(full_path)

    def get_repo_override(self):
        """Return the repository override value."""
        return self.__repoEdit.text().strip()

    def get_clone_to(self):
        """Return the clone target directory."""
        return self.__cloneToEdit.text().strip()

    def get_open_after_clone(self):
        """Return whether to open project after clone."""
        return self.__openAfterCb.isChecked()
