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

"""Git VCS plugin for Codimension.

Provides: status, commit, push, pull, add, branch operations.
"""

import os
import tempfile

from packaging.version import Version
from plugins.categories.vcsiface import VersionControlSystemInterface
from ui.qt import QDialog, QMessageBox, pyqtSignal

from .gitdriver import find_git_root, run_git
from .gitstatusparser import (
    IND_ADDED,
    IND_CLEAN,
    IND_CONFLICT,
    IND_DELETED,
    IND_MODIFIED,
    IND_UNTRACKED,
    parse_status_output,
)


class GitPlugin(VersionControlSystemInterface):
    """Git VCS plugin."""

    PathChanged = pyqtSignal(str)

    def __init__(self):
        VersionControlSystemInterface.__init__(self)
        self.__dirParentMenu = None
        self.__fileParentMenu = None

    @staticmethod
    def isIDEVersionCompatible(ideVersion):
        """Check if the IDE version is compatible with the plugin."""
        return Version(ideVersion) >= Version("4.7.1")

    @staticmethod
    def getVCSName():
        """Return the VCS name."""
        return "Git"

    def activate(self, ideSettings, ideGlobalData):
        """Activate the plugin."""
        VersionControlSystemInterface.activate(self, ideSettings, ideGlobalData)

    def deactivate(self):
        """Deactivate the plugin."""
        VersionControlSystemInterface.deactivate(self)

    def getCustomIndicators(self):
        """Return custom status indicators.

        Format: (id, pixmap_or_text, foreground, background, tooltip)
        """
        return [
            (IND_MODIFIED, "M", "200,100,0,255", "255,240,200,255", "Modified"),
            (IND_ADDED, "A", "0,128,0,255", "220,255,220,255", "Added"),
            (IND_DELETED, "D", "180,0,0,255", "255,220,220,255", "Deleted"),
            (IND_UNTRACKED, "?", "100,100,100,255", "240,240,240,255", "Untracked"),
            (IND_CONFLICT, "U", "180,0,0,255", "255,200,200,255", "Conflict"),
            (IND_CLEAN, ".", None, None, "Clean"),
        ]

    def getStatus(self, path, flag):
        """Return VCS status for path.

        Called from VCSPluginThread - no IDE/UI calls allowed.
        """
        git_root = find_git_root(path)
        if git_root is None:
            if flag == VersionControlSystemInterface.REQUEST_ITEM_ONLY:
                return [("", VersionControlSystemInterface.NOT_UNDER_VCS, None)]
            return []

        stdout, _stderr, returncode = run_git(git_root, ["status", "--porcelain"])
        if returncode != 0:
            if flag == VersionControlSystemInterface.REQUEST_ITEM_ONLY:
                return [("", VersionControlSystemInterface.NOT_UNDER_VCS, None)]
            return []

        parsed = parse_status_output(git_root, stdout)
        return self._filter_and_convert(path, flag, git_root, parsed)

    def _filter_and_convert(self, requested_path, flag, git_root, parsed):
        """Filter parsed items by requested path and convert to (rest, id, msg)."""
        root = git_root.rstrip(os.path.sep) + os.path.sep
        req = os.path.normpath(requested_path)

        if flag == VersionControlSystemInterface.REQUEST_ITEM_ONLY:
            for rel, ind_id, msg in parsed:
                full = os.path.normpath(root.rstrip(os.path.sep) + os.path.sep + rel)
                if full == req or full.rstrip(os.path.sep) == req.rstrip(os.path.sep):
                    return [("", ind_id, msg)]
            if req.startswith(root.rstrip(os.path.sep)):
                return [("", IND_CLEAN, None)]
            return [("", VersionControlSystemInterface.NOT_UNDER_VCS, None)]

        result = []
        prefix = req.rstrip(os.path.sep) + os.path.sep
        for rel, ind_id, msg in parsed:
            full = os.path.normpath(root.rstrip(os.path.sep) + os.path.sep + rel)
            if not full.startswith(prefix):
                continue
            rest = full[len(prefix) :]
            if os.path.isdir(full) and not rest.endswith(os.path.sep):
                rest = rest + os.path.sep
            result.append((rest, ind_id, msg))
        return result

    def populateMainMenu(self, parentMenu):
        """Populate the main menu: Git/GitHub actions. Settings via Plugin Manager only."""
        from utils.pixmapcache import getIcon

        parentMenu.setIcon(getIcon("pluginsettings.png"))
        parentMenu.addAction("Switch branch", self.__onSwitchBranch)
        parentMenu.addAction("Create pull request...", self.__onCreatePR)
        parentMenu.addAction("View pull requests", self.__onViewPRs)

    def populateFileContextMenu(self, parentMenu):
        """Populate the file context menu."""
        self.__fileParentMenu = parentMenu
        parentMenu.addAction("Add", self.__onFileAdd)
        parentMenu.addAction("Discard changes", self.__onFileDiscard)
        parentMenu.addAction("Show diff", self.__onFileDiff)

    def populateDirectoryContextMenu(self, parentMenu):
        """Populate the directory context menu (Project → Git)."""
        self.__dirParentMenu = parentMenu
        parentMenu.addAction("Commit", self.__onDirCommit)
        parentMenu.addAction("Push", self.__onDirPush)
        parentMenu.addAction("Pull", self.__onDirPull)
        parentMenu.addAction("Create branch", self.__onDirCreateBranch)
        parentMenu.addAction("Switch branch", self.__onDirSwitchBranch)
        parentMenu.addSeparator()
        parentMenu.addAction("Create pull request...", self.__onDirCreatePR)
        parentMenu.addAction("View pull requests", self.__onDirViewPRs)

    def populateBufferContextMenu(self, parentMenu):
        """Populate the buffer context menu."""
        del parentMenu

    def getConfigFunction(self):
        """Return config dialog callable for git path, gh path, default remote."""
        return self.__configure

    def __configure(self):
        """Open Git configuration dialog."""
        from .gitconfig import GitConfigDialog, save_config

        dlg = GitConfigDialog(self.ide.mainWindow)
        if dlg.exec_() == QDialog.Accepted:
            save_config(*dlg.get_values())

    def __get_repo_path(self):
        """Get path for Git/GitHub ops: project dir or current file dir."""
        if self.ide.project.isLoaded():
            return self.ide.project.getProjectDir()
        widget = self.ide.currentEditorWidget
        if widget is not None and hasattr(widget, "getFileName"):
            path = widget.getFileName()
            if path and os.path.isabs(path):
                return os.path.dirname(path) + os.path.sep
        return os.getcwd() + os.path.sep

    def __onCreatePR(self):
        """Create pull request from current branch."""
        path = self.__get_repo_path()
        root = find_git_root(path)
        if root is None:
            QMessageBox.warning(
                self.ide.mainWindow,
                "Git",
                "Not a Git repository. Open a project or file in a Git repo.",
            )
            return
        from .gitdialogs import CreatePRDialog

        dlg = CreatePRDialog(root, self.ide.mainWindow)
        if dlg.exec_() != QDialog.Accepted:
            return
        base, title, body = dlg.get_values()
        if not title.strip():
            QMessageBox.warning(
                self.ide.mainWindow, "Git", "PR title is required."
            )
            return
        from .githubapi import create_pull_request

        url, err = create_pull_request(root, base.strip() or "main", title.strip(), body.strip())
        if err:
            QMessageBox.warning(self.ide.mainWindow, "Git", err)
            return
        self.ide.showStatusBarMessage("PR created: " + (url or ""), 5000)
        if url:
            self.PathChanged.emit(root)

    def __onViewPRs(self):
        """View pull requests in browser or output."""
        path = self.__get_repo_path()
        root = find_git_root(path) if path else None
        from .githubapi import get_repo_prs_url

        url = get_repo_prs_url(root)
        if not url:
            QMessageBox.warning(
                self.ide.mainWindow,
                "Git",
                "Could not determine GitHub repo URL from remote.",
            )
            return
        from ui.qt import QDesktopServices, QUrl

        QDesktopServices.openUrl(QUrl(url))

    def __get_path_from_menu(self, parent_menu):
        """Get the selected path from the parent menu data."""
        if parent_menu is None:
            return None
        data = parent_menu.menuAction().data()
        if data is None:
            return None
        try:
            return str(data) if not hasattr(data, "toString") else data.toString()
        except Exception:
            return None

    def __run_git_op(self, path, args, success_msg="Done"):
        """Run git command and refresh status on success."""
        root = find_git_root(path)
        if root is None:
            QMessageBox.warning(
                self.ide.mainWindow,
                "Git",
                "Not a Git repository.",
            )
            return False
        stdout, stderr, code = run_git(root, args)
        if code != 0:
            QMessageBox.warning(
                self.ide.mainWindow,
                "Git",
                stderr or stdout or "Command failed.",
            )
            return False
        self.PathChanged.emit(root)
        self.ide.showStatusBarMessage(success_msg, 3000)
        return True

    def __onFileAdd(self):
        """Add file to index."""
        path = self.__get_path_from_menu(self.__fileParentMenu)
        if path and self.__run_git_op(path, ["add", path], "Added"):
            pass

    def __onFileDiscard(self):
        """Discard changes in file."""
        path = self.__get_path_from_menu(self.__fileParentMenu)
        if not path:
            return
        if QMessageBox.question(
            self.ide.mainWindow,
            "Git",
            "Discard changes in " + os.path.basename(path) + "?",
            QMessageBox.StandardButtons(QMessageBox.Yes | QMessageBox.No),
            QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        self.__run_git_op(path, ["checkout", "--", path], "Changes discarded")

    def __onFileDiff(self):
        """Show diff for file."""
        path = self.__get_path_from_menu(self.__fileParentMenu)
        if not path:
            return
        root = find_git_root(path)
        if root is None:
            QMessageBox.warning(self.ide.mainWindow, "Git", "Not a Git repository.")
            return
        rel = os.path.relpath(path, root)
        stdout, stderr, code = run_git(root, ["diff", rel])
        if code != 0:
            QMessageBox.warning(self.ide.mainWindow, "Git", stderr or "Diff failed.")
            return
        content = stdout or "(no changes)"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".diff", delete=False, prefix="gitdiff_"
        ) as f:
            f.write(content)
            tmp_path = f.name
        try:
            self.ide.mainWindow.openFile(tmp_path, -1)
        except Exception:
            os.unlink(tmp_path)
            raise

    def __onDirCommit(self):
        """Commit changes."""
        path = self.__get_path_from_menu(self.__dirParentMenu)
        if not path:
            return
        root = find_git_root(path)
        if root is None:
            QMessageBox.warning(self.ide.mainWindow, "Git", "Not a Git repository.")
            return
        from .gitdialogs import CommitDialog

        dlg = CommitDialog(self.ide.mainWindow)
        if dlg.exec_() != QDialog.Accepted:
            return
        msg = dlg.get_message()
        if not msg.strip():
            QMessageBox.warning(self.ide.mainWindow, "Git", "Commit message is required.")
            return
        args = ["commit", "-m", msg.strip()]
        if dlg.get_amend():
            args.append("--amend")
        if self.__run_git_op(path, args, "Committed"):
            pass

    def __onDirPush(self):
        """Push to remote."""
        path = self.__get_path_from_menu(self.__dirParentMenu)
        if path and self.__run_git_op(path, ["push"], "Pushed"):
            pass

    def __onDirPull(self):
        """Pull from remote."""
        path = self.__get_path_from_menu(self.__dirParentMenu)
        if path and self.__run_git_op(path, ["pull"], "Pulled"):
            pass

    def __onDirCreateBranch(self):
        """Create a new branch."""
        path = self.__get_path_from_menu(self.__dirParentMenu)
        if not path:
            return
        root = find_git_root(path)
        if root is None:
            QMessageBox.warning(self.ide.mainWindow, "Git", "Not a Git repository.")
            return
        from .gitdialogs import CreateBranchDialog

        dlg = CreateBranchDialog(root, self.ide.mainWindow)
        if dlg.exec_() != QDialog.Accepted:
            return
        name = dlg.get_branch_name()
        if not name.strip():
            QMessageBox.warning(self.ide.mainWindow, "Git", "Branch name is required.")
            return
        if self.__run_git_op(path, ["checkout", "-b", name.strip()], "Branch created"):
            pass

    def __onDirSwitchBranch(self):
        """Switch to selected branch."""
        path = self.__get_path_from_menu(self.__dirParentMenu)
        if not path:
            return
        root = find_git_root(path)
        if root is None:
            QMessageBox.warning(self.ide.mainWindow, "Git", "Not a Git repository.")
            return
        from .gitdialogs import SelectBranchDialog

        dlg = SelectBranchDialog(root, self.ide.mainWindow)
        if dlg.exec_() != QDialog.Accepted:
            return
        branch = dlg.get_selected_branch()
        if not branch:
            return
        args = ["checkout", branch]
        if branch.startswith("origin/"):
            args = ["checkout", "--track", branch]
        if self.__run_git_op(path, args, "Switched to " + branch):
            pass

    def __onSwitchBranch(self):
        """Switch branch from main menu."""
        path = self.__get_repo_path()
        root = find_git_root(path)
        if root is None:
            QMessageBox.warning(
                self.ide.mainWindow,
                "Git",
                "Not a Git repository. Open a project or file in a Git repo.",
            )
            return
        from .gitdialogs import SelectBranchDialog

        dlg = SelectBranchDialog(root, self.ide.mainWindow)
        if dlg.exec_() != QDialog.Accepted:
            return
        branch = dlg.get_selected_branch()
        if not branch:
            return
        args = ["checkout", branch]
        if branch.startswith("origin/"):
            args = ["checkout", "--track", branch]
        if self.__run_git_op(path, args, "Switched to " + branch):
            pass

    def __onDirCreatePR(self):
        """Create PR from directory context."""
        path = self.__get_path_from_menu(self.__dirParentMenu)
        if not path:
            return
        root = find_git_root(path)
        if root is None:
            QMessageBox.warning(self.ide.mainWindow, "Git", "Not a Git repository.")
            return
        from .gitdialogs import CreatePRDialog

        dlg = CreatePRDialog(root, self.ide.mainWindow)
        if dlg.exec_() != QDialog.Accepted:
            return
        base, title, body = dlg.get_values()
        if not title.strip():
            QMessageBox.warning(self.ide.mainWindow, "Git", "PR title is required.")
            return
        from .githubapi import create_pull_request

        url, err = create_pull_request(root, base.strip() or "main", title.strip(), body.strip())
        if err:
            QMessageBox.warning(self.ide.mainWindow, "Git", err)
            return
        self.ide.showStatusBarMessage("PR created: " + (url or ""), 5000)
        if url:
            self.PathChanged.emit(root)

    def __onDirViewPRs(self):
        """View PRs from directory context."""
        path = self.__get_path_from_menu(self.__dirParentMenu)
        if not path:
            return
        root = find_git_root(path)
        if root is None:
            QMessageBox.warning(self.ide.mainWindow, "Git", "Not a Git repository.")
            return
        from ui.qt import QDesktopServices, QUrl

        from .githubapi import get_repo_prs_url

        url = get_repo_prs_url(root)
        if not url:
            QMessageBox.warning(
                self.ide.mainWindow,
                "Git",
                "Could not determine GitHub repo URL from remote.",
            )
            return
        QDesktopServices.openUrl(QUrl(url))
