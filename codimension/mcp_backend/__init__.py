# -*- coding: utf-8 -*-
#
# codimension - MCP / remote agent backend (R182)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Headless MCP surface over Codimension core (R182 / R214).

Package name is ``mcp_backend`` (not ``mcp``) so it does not shadow the
optional Model Context Protocol SDK package on ``sys.path``.

Optional install: ``pip install 'codimension[mcp]'`` then run
``codimension-mcp --workspace /path/to/project`` with ``CDM_MCP_TOKEN`` set
(fail-closed). The workspace root is immutable for the process lifetime.
"""

from __future__ import annotations

__all__ = ["__version_note__"]

#: Marker for Living Spec / diagnostics (not PEP 440 package version).
__version_note__ = "r214"
