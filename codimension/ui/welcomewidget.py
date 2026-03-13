# -*- coding: utf-8 -*-
#
# codimension - graphics Python two-way code editor and analyzer
# Copyright (C) 2010-2025  Sergey Satskiy <sergey.satskiy@gmail.com>
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

"""Welcome screen"""

import os.path
import sys

from utils.globals import GlobalData
from utils.project import CodimensionProject

from .texttabwidget import TextTabWidget


# Primary: active fork. Secondary: original (unmaintained).
FORK_URL = "https://github.com/sesquicadaver/codimension"
ORIGINAL_URL = "http://codimension.org"


class WelcomeWidget(TextTabWidget):
    """Welcome screen"""

    httpAddress = FORK_URL

    def __init__(self, parent=None):
        TextTabWidget.__init__(self, parent)
        self.setHTML(self.__getContent())
        self.setFileName("")
        self.setShortName("Welcome")
        GlobalData().project.sigProjectChanged.connect(self.__onProjectChanged)

    def __onProjectChanged(self, what):
        if what == CodimensionProject.CompleteProject:
            self.setHTML(self.__getContent())

    def __getContent(self):
        project = GlobalData().project
        projectMDFile = project.getStartupMarkdownFile()

        projectPart = ""
        if projectMDFile:
            if os.path.exists(projectMDFile):
                relativeMDFile = project.getRelativePath(projectMDFile)
                projectPart = (
                    """<p align="left">The currently loaded project
<b>"""
                    + GlobalData().project.getProjectName()
                    + """</b> provides documentation.
<br>Open it by clicking
<a href="action://project-documentation">"""
                    + relativeMDFile
                    + """</a>
or clicking any time the main toolbar button with the markdown icon.</p>

<br>
<hr>
<br>"""
                )

        pixmapPath = os.path.dirname(os.path.realpath(sys.argv[0])) + os.path.sep + "pixmaps" + os.path.sep
        logoPath = pixmapPath + "logo-48x48.png"
        welcome = (
            "  Codimension version "
            + str(GlobalData().version)
            + " <font size=-2>(GPL v3)</font>"
            + " <font size=-2>— Modified version</font>"
        )

        return (
            """
<body bgcolor="#EFF0F2">
<p>
<table cellspacing="0" cellpadding="8" width="100%"
       align="left" bgcolor="#EFF0F2" border="0" style="width: 100%">
<tr>
  <td width="1%" valign="middle">
      <a href='"""
            + FORK_URL
            + """'>
      <img border="0" align="left" src='file:"""
            + logoPath
            + """'
           width="48" height="48">
      </a>
  </td>
  <td valign="middle">
      <h2 align="left">&nbsp;"""
            + welcome
            + """</h2>
  </td>
</tr>
</table>
<br><br>
<table cellspacing="0" cellpadding="8" width="100%"
       align="left" bgcolor="#EFF0F2" border="0" style="width: 100%">
<tr>
  <td>"""
            + projectPart
            + """
    <p align="left">Press <b>F1</b> any time for the Keyboard Shortcut
       Reference or follow this <a href="action://F1">link</a>.</p>
    <p align="left">The IDE also features the documentation available
       via the main menu <i>Help -> Documentation</i> or via following this
       <a href="action://embedded-help">link</a>.</p>

    <br>
    <hr>
    <br>

    <p align="left">
       More information:
       <a href='"""
            + FORK_URL
            + """'>GitHub (fork)</a>,
       <a href='"""
            + ORIGINAL_URL
            + """'>Codimension home page (archive)</a>.
    </p>
  </td>
</tr>
</table></p>
</body>"""
        )
