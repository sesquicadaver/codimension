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

"""Utils to work with binary files"""

import logging
import os.path
import subprocess

from .globals import GlobalData


def getHexdump(fileName):
    """Provides the hex dumped file content or None.

    Uses the system ``hexdump -C`` utility when available.
    """
    if not GlobalData().hexdumpAvailable:
        logging.error("hexdump is not available")
        return None
    if not fileName or not os.path.isfile(fileName):
        logging.error("Cannot hexdump: file does not exist: %s", fileName)
        return None
    try:
        result = subprocess.run(
            ["hexdump", "-C", fileName],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logging.error("hexdump failed for %s: %s", fileName, exc)
        return None
    if result.returncode != 0:
        logging.error("hexdump exited %s: %s", result.returncode, result.stderr.strip())
        return None
    return result.stdout
