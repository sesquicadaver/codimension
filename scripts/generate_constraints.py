#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate ``constraints.txt`` from a clean venv install of ``.[dev]`` (D08).

Creates a temporary virtualenv, installs the project with all optional groups,
freezes non-editable pins, and writes ``constraints.txt`` at the repo root.

Prefer generating with **Python 3.10** (lowest CI matrix) so pins resolve on
3.10–3.13. If a pin's ``Requires-Python`` excludes 3.10, lower it before commit.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

PIN_RE = re.compile(r"^[A-Za-z0-9_.\-]+==[^=]+$")


def _run(cmd: list[str], *, cwd: Path) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.check_call(cmd, cwd=str(cwd))


def generate(root: Path, python: str) -> Path:
    """Return path to the written ``constraints.txt``."""
    out_path = root / "constraints.txt"
    with tempfile.TemporaryDirectory(prefix="cdm-constraints-") as tmp:
        venv_dir = Path(tmp) / "venv"
        venv.create(str(venv_dir), with_pip=True, symlinks=True)
        pip = str(venv_dir / ("Scripts" if sys.platform == "win32" else "bin") / "pip")
        py = str(venv_dir / ("Scripts" if sys.platform == "win32" else "bin") / "python")
        _run([py, "-m", "pip", "install", "--upgrade", "pip"], cwd=root)
        _run([pip, "install", "-e", ".[dev]"], cwd=root)
        freeze = subprocess.check_output(
            [pip, "freeze", "--exclude-editable"],
            cwd=str(root),
            text=True,
        )
    pins: list[str] = []
    for line in freeze.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or " @ " in line or line.startswith("file:"):
            continue
        if line.lower().startswith("codimension=="):
            continue
        if PIN_RE.match(line):
            pins.append(line)
    pins = sorted(set(pins), key=str.lower)
    body = (
        "# Generated dependency snapshot for CI/dev (D08).\n"
        "# Regenerate: python scripts/generate_constraints.py\n"
        "# Runtime metadata ranges stay in pyproject.toml / requirements*.txt\n"
        + "\n".join(pins)
        + "\n"
    )
    out_path.write_text(body, encoding="utf-8")
    print(f"Wrote {out_path} ({len(pins)} pins)", flush=True)
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()
    generate(args.root.resolve(), args.python)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
