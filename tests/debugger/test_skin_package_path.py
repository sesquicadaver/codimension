# -*- coding: utf-8 -*-
"""T130: PACKAGE_SKIN_DIR resolves from the package tree (not sys.argv[0])."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def test_package_skin_dir_points_at_codimension_skins(monkeypatch):
    """Skins live under ``codimension/skins/`` regardless of launcher argv."""
    import parsers  # noqa: F401
    import utils.skin as skin_mod

    monkeypatch.setattr(sys, "argv", ["/nonexistent/pytest-launcher", *sys.argv[1:]])

    pkg_skins = Path(skin_mod.PACKAGE_SKIN_DIR)
    assert pkg_skins.is_dir(), f"missing package skins: {pkg_skins}"
    assert pkg_skins.name == "skins"
    assert pkg_skins.parent.name == "codimension"
    # Must not resolve relative to the fake argv launcher.
    assert "pytest-launcher" not in str(pkg_skins)
    assert os.path.isdir(skin_mod.PACKAGE_SKIN_DIR)
