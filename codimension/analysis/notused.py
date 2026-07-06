# -*- coding: utf-8 -*-
#
# codimension - graphics python two-way code editor and analyzer
# Copyright (C) 2012-2018  Sergey Satskiy <sergey.satskiy@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#


"""not used code analysis using vulture"""

import logging
import os
import os.path
import sys
import tempfile
from subprocess import PIPE, Popen

from search.searchsupport import ItemToSearchIn, getSearchItemIndex
from search.vultureprovider import VultureSearchProvider
from ui.qt import QApplication, QCursor, QDialog, QDialogButtonBox, QLabel, Qt, QTimer, QVBoxLayout
from utils.config import DEFAULT_ENCODING
from utils.globals import GlobalData
from utils.venvutils import getProjectVenvDir


class NotUsedAnalysisProgress(QDialog):
    """Progress of the not used analysis"""

    def __init__(self, path, newSearch=True):
        QDialog.__init__(self, GlobalData().mainWindow)

        path = os.path.abspath(path)
        if not os.path.exists(path):
            raise Exception('Dead code analysis path must exist. The provide path "' + path + '" does not.')

        self.__path = path

        self.__newSearch = newSearch
        self.candidates = None
        self.__cancelRequest = False
        self.__inProgress = False

        self.__infoLabel = None
        self.__foundLabel = None
        self.__found = 0  # Number of found

        self.__createLayout()
        title = "Dead code analysis for "
        if os.path.isdir(path):
            project = GlobalData().project
            if project.isLoaded() and project.getProjectDir() == path:
                title += "all project files"
            else:
                title += "dir " + os.path.basename(os.path.normpath(path))
        else:
            title += os.path.basename(path)

        if not self.__newSearch:
            title += " (do again)"

        self.setWindowTitle(title)
        self.__updateFoundLabel()

    def exec_(self):
        """Executes the dialog"""
        QTimer.singleShot(1, self.__process)
        QDialog.exec_(self)

    def keyPressEvent(self, event):
        """Processes the ESC key specifically"""
        if event.key() == Qt.Key_Escape:
            self.__onClose()
        else:
            QDialog.keyPressEvent(self, event)

    def __updateFoundLabel(self):
        """Updates the found label"""
        text = "Found: " + str(self.__found) + " candidate"
        if self.__found != 1:
            text += "s"
        self.__foundLabel.setText(text)

    def __createLayout(self):
        """Creates the dialog layout"""
        self.resize(450, 20)
        self.setSizeGripEnabled(True)

        verticalLayout = QVBoxLayout(self)

        # Note label
        noteLabel = QLabel(
            "<b>Note</b>: the analysis is suggestive and not precise. Use the results with caution.\n", self
        )
        verticalLayout.addWidget(noteLabel)

        # Info label
        self.__infoLabel = QLabel(self)
        verticalLayout.addWidget(self.__infoLabel)

        # Found label
        self.__foundLabel = QLabel(self)
        verticalLayout.addWidget(self.__foundLabel)

        # Buttons
        buttonBox = QDialogButtonBox(self)
        buttonBox.setOrientation(Qt.Horizontal)
        buttonBox.setStandardButtons(QDialogButtonBox.Close)
        verticalLayout.addWidget(buttonBox)

        buttonBox.rejected.connect(self.__onClose)

    def __onClose(self):
        """triggered when the close button is clicked"""
        self.__cancelRequest = True
        if not self.__inProgress:
            self.close()

    def _get_exclude_patterns(self):
        """Build comma-separated exclude patterns for vulture."""
        patterns = [".venv", "venv", "__pycache__"]
        project = GlobalData().project
        if project.isLoaded() and project.getProjectDir() == self.__path:
            venv_dir = getProjectVenvDir(project)
            if venv_dir:
                patterns.append(venv_dir)
            for excl in project.getExcludeFromAnalysisAsAbsolutePaths():
                if excl:
                    patterns.append(excl)
        return ",".join(patterns)

    def _get_dead_code_dir(self):
        """Return absolute path to deadCode directory in the analyzed project root."""
        project = GlobalData().project
        if project.isLoaded():
            proj_dir = project.getProjectDir()
            # Use project root when analyzing project or a file within it
            if self.__path == proj_dir or project.isProjectDir(self.__path):
                return os.path.join(proj_dir, "deadCode")
            if os.path.isfile(self.__path) and project.isProjectFile(self.__path):
                return os.path.join(proj_dir, "deadCode")
        base = os.path.dirname(self.__path) if os.path.isfile(self.__path) else self.__path
        return os.path.join(base, "deadCode")

    def _get_report_base_path(self):
        """Return base path for relative file paths in the report."""
        dead_code_dir = self._get_dead_code_dir()
        return os.path.dirname(dead_code_dir)

    def _save_dead_code_report(self):
        """Save dead code candidates to deadCode/deadcode.txt.
        Uses paths relative to the analyzed project root."""
        if not self.candidates:
            return
        dead_code_dir = self._get_dead_code_dir()
        try:
            os.makedirs(dead_code_dir, exist_ok=True)
        except OSError as exc:
            logging.warning("Cannot create deadCode dir %s: %s", dead_code_dir, exc)
            return
        out_path = os.path.join(dead_code_dir, "deadcode.txt")
        base_path = self._get_report_base_path()
        lines = []
        for item in self.candidates:
            try:
                rel_path = os.path.relpath(item.fileName, base_path)
            except ValueError:
                rel_path = item.fileName
            for match in item.matches:
                lines.append("%s:%d: %s" % (rel_path, match.line, match.text or ""))
        try:
            with open(out_path, "w", encoding=DEFAULT_ENCODING) as f:
                f.write("\n".join(lines))
                if lines:
                    f.write("\n")
            logging.info("Dead code report saved to %s", out_path)
        except OSError as exc:
            logging.warning("Cannot write dead code report to %s: %s", out_path, exc)

    def _get_pyproject_config(self):
        """Return path to pyproject.toml with [tool.vulture] if present."""
        base = self._get_report_base_path()
        config_path = os.path.join(base, "pyproject.toml")
        if not os.path.isfile(config_path):
            return None
        try:
            with open(config_path, encoding=DEFAULT_ENCODING) as f:
                content = f.read()
            if "[tool.vulture]" in content or "[tool.vulture]" in content:
                return config_path
        except OSError:
            pass
        return None

    def _log_vulture_stderr(self, stderr):
        """Surface vulture diagnostics with the analyzed path for context."""
        if not stderr:
            return
        for line in stderr.splitlines():
            line = line.strip()
            if not line:
                continue
            if "SyntaxWarning" in line or "invalid escape" in line:
                logging.warning("Dead code analysis (%s): %s", self.__path, line)
            else:
                logging.error("Dead code analysis (%s): %s", self.__path, line)

    def __run(self):
        """Runs vulture via current Python interpreter (same venv as IDE)."""
        errTmp = tempfile.mkstemp()
        errStream = os.fdopen(errTmp[0])
        cmd = [sys.executable, "-m", "vulture"]
        config_path = self._get_pyproject_config()
        if config_path:
            cmd.extend(["--config", config_path])
        if os.path.isdir(self.__path):
            exclude_patterns = self._get_exclude_patterns()
            if exclude_patterns:
                cmd.extend(["--exclude", exclude_patterns])
        cmd.append(self.__path)
        process = Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=errStream)
        process.stdin.close()
        processStdout = process.stdout.read()
        process.stdout.close()
        errStream.seek(0)
        err = errStream.read()
        errStream.close()
        process.wait()
        try:
            os.unlink(errTmp[1])
        except OSError:
            pass
        return processStdout.decode(DEFAULT_ENCODING), err.strip()

    def __process(self):
        """Analysis process"""
        self.__inProgress = True
        mainWindow = GlobalData().mainWindow

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        # return code gives really nothing. So the error in running the utility
        # is detected by the stderr content.
        # Also, there could be a mix of messages for a project. Some files
        # could have syntax errors - there will be messages on stderr. The
        # other files are fine so there will be messages on stdout
        stdout, stderr = self.__run()
        self.candidates = []
        for line in stdout.splitlines():
            line = line.strip()
            if line:
                # Line is like file.py:2: unused variable 'a' (60% confidence)
                try:
                    startIndex = line.find(":")
                    if startIndex < 0:
                        continue
                    endIndex = line.find(":", startIndex + 1)
                    if endIndex < 0:
                        continue
                    fileName = line[:startIndex]
                    startIndex = line.find(":")
                    if startIndex < 0:
                        continue
                    endIndex = line.find(":", startIndex + 1)
                    if endIndex < 0:
                        continue
                    fileName = os.path.abspath(line[:startIndex])
                    lineno = int(line[startIndex + 1 : endIndex])
                    message = line[endIndex + 1 :].strip()
                except (ValueError, IndexError):
                    continue

                index = getSearchItemIndex(self.candidates, fileName)
                if index < 0:
                    widget = mainWindow.getWidgetForFileName(fileName)
                    if widget is None:
                        uuid = ""
                    else:
                        uuid = widget.getUUID()
                    newItem = ItemToSearchIn(fileName, uuid)
                    self.candidates.append(newItem)
                    index = len(self.candidates) - 1
                self.candidates[index].addMatch("", lineno, message)

                self.__found += 1
                self.__updateFoundLabel()
                QApplication.processEvents()

        if self.__newSearch:
            # Do the action only for the new search.
            # Redo action will handle the results on its own
            if stderr:
                self._log_vulture_stderr(stderr)
            if self.__found == 0:
                if not stderr:
                    logging.info("No unused candidates found")
            else:
                mainWindow.displayFindInFiles(VultureSearchProvider.getName(), self.candidates, {"path": self.__path})
        if self.candidates:
            self._save_dead_code_report()

        QApplication.restoreOverrideCursor()
        self.__infoLabel.setText("Done")
        self.__inProgress = False

        self.accept()
