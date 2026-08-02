#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Headless QApplication smoke (T066). Exit 0 if Qt starts under offscreen platform."""

from __future__ import annotations

import os
import sys


def main() -> int:
    """Create QApplication and quit immediately."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    # Ensure package imports resolve when run from repo root
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if root not in sys.path:
        sys.path.insert(0, root)
    # Legacy top-level shims used by the IDE
    codim = os.path.join(root, "codimension")
    if codim not in sys.path:
        sys.path.insert(0, codim)

    from PyQt5.QtWidgets import QApplication

    app = QApplication([])
    app.processEvents()
    print("offscreen_gui_smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
