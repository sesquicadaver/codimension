# -*- coding: utf-8 -*-
#
# codimension - graphics python two-way code editor and analyzer
# Copyright (C) 2019  Sergey Satskiy <sergey.satskiy@gmail.com>
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

"""Codimension pylint stdout/stderr viewer"""

from ui.qt import (QDialog, QVBoxLayout, QHBoxLayout, Qt, QProcess,
                   QSizePolicy, QLabel, QDialogButtonBox, QTextEdit)
from ui.labels import HeaderFitLabel
from utils.colorfont import getZoomedMonoFont


class PylintStdoutStderrViewer(QDialog):

    """Shows the standard output and error if so"""

    def __init__(self, parent, results):
        QDialog.__init__(self, parent)

        title = 'pylint raw'
        stdout = results.get('StdOut', None)
        stderr = results.get('StdErr', None)

        if stdout is not None and stderr is not None:
            title += ' standard output and standard error'
        elif stdout is not None:
            title += ' standard output'
        else:
            title += ' standard error'
        self.setWindowTitle(title)
        self.__createLayout(results)

    def __createLayout(self, results):
        """Creates the layout"""
        self.resize(600, 250)
        self.setSizeGripEnabled(True)

        layout = QVBoxLayout(self)

        headerLayout = QHBoxLayout()
        headerLayout.setSpacing(4)

        statusLabel = HeaderFitLabel(self)
        statusLabel.setAlignment(Qt.AlignLeft)
        statusLabel.setSizePolicy(QSizePolicy.Expanding,
                                  QSizePolicy.Fixed)
        statusLabel.setMinimumWidth(10)
        if 'ExitStatus' in results:
            if results['ExitStatus'] == QProcess.NormalExit:
                statusLabel.setText('Exit status: normal exit')
            else:
                statusLabel.setText('Exit status: crash exit')
        else:
            statusLabel.setText('Exit status: not available')

        exitCodeLabel = HeaderFitLabel(self)
        exitCodeLabel.setAlignment(Qt.AlignLeft)
        exitCodeLabel.setSizePolicy(QSizePolicy.Expanding,
                                    QSizePolicy.Fixed)
        exitCodeLabel.setMinimumWidth(10)
        if 'ExitCode' in results:
            if 'ExitStatus' in results:
                if results['ExitStatus'] == QProcess.NormalExit:
                    exitCodeLabel.setText('Exit code: ' +
                                          str(results['ExitCode']))
                else:
                    exitCodeLabel.setText('Exit code: not available')
            else:
                exitCodeLabel.setText('Exit code: not available')
        else:
            exitCodeLabel.setText('Exit code: not available')

        headerLayout.addWidget(statusLabel)
        headerLayout.addWidget(exitCodeLabel)
        layout.addLayout(headerLayout)

        stdout = results.get('StdOut', None)
        if stdout is None:
            stdoutLabel = QLabel('Standard output: not available', self)
            layout.addWidget(stdoutLabel)
        else:
            stdoutLabel = QLabel('Standard output:', self)
            layout.addWidget(stdoutLabel)

            stdoutEditor = QTextEdit()
            stdoutEditor.setReadOnly(True)
            stdoutEditor.setFont(getZoomedMonoFont())
            stdoutEditor.setAcceptRichText(False)
            stdoutEditor.setPlainText(stdout)
            layout.addWidget(stdoutEditor)

        stderr = results.get('StdErr', None)
        if stderr is None:
            stderrLabel = QLabel('Standard error: not available', self)
            layout.addWidget(stderrLabel)
        else:
            stderrLabel = QLabel('Standard error:', self)
            layout.addWidget(stderrLabel)

            stderrEditor = QTextEdit()
            stderrEditor.setReadOnly(True)
            stderrEditor.setFont(getZoomedMonoFont())
            stderrEditor.setAcceptRichText(False)
            stderrEditor.setPlainText(stderr)
            layout.addWidget(stderrEditor)

        # Buttons at the bottom
        buttonBox = QDialogButtonBox(self)
        buttonBox.setOrientation(Qt.Horizontal)
        buttonBox.setStandardButtons(QDialogButtonBox.Ok)
        self.__OKButton = buttonBox.button(QDialogButtonBox.Ok)
        self.__OKButton.setDefault(True)
        buttonBox.accepted.connect(self.close)
        buttonBox.rejected.connect(self.close)
        layout.addWidget(buttonBox)

