# -*- coding: utf-8 -*-
"""Pytest configuration for Codimension tests."""

import os
import sys

# Ensure project root and codimension package dir are in path (cdmplugins imports plugins, ui, utils)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODMENSION_DIR = os.path.join(ROOT, "codimension")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if CODMENSION_DIR not in sys.path:
    sys.path.insert(0, CODMENSION_DIR)
