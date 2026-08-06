# -*- coding: utf-8 -*-
#
# codimension - headless process environment dicts (T082/R112)
#

"""Build subprocess environment mappings without Qt (headless tools)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from utils.analysis_environment import AnalysisEnvironment


def build_tool_environ(
    encoding: str = "utf-8",
    overrides: Mapping[str, str] | None = None,
    *,
    analysis_env: Optional[AnalysisEnvironment] = None,
    base: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return a ``dict`` suitable for ``subprocess`` ``env=``.

    Mirrors the intent of ``cdmplugins.process_env.build_tool_process_environment``
    without requiring ``QProcessEnvironment`` / Qt.

    When ``analysis_env`` is set, prepends site-packages to ``PYTHONPATH`` and
    sets ``VIRTUAL_ENV`` for venv interpreters (R112).
    """
    env = dict(base if base is not None else os.environ)
    env["PYTHONIOENCODING"] = encoding or "utf-8"
    if analysis_env is not None:
        from utils.analysis_environment import tool_environ_overrides

        tool_over = tool_environ_overrides(analysis_env)
        pythonpath = tool_over.pop("PYTHONPATH", None)
        if pythonpath:
            existing = env.get("PYTHONPATH", "") or ""
            env["PYTHONPATH"] = pythonpath if not existing else pythonpath + os.pathsep + existing
        env.update(tool_over)
    if overrides:
        for key, value in overrides.items():
            env[str(key)] = str(value)
    return env
