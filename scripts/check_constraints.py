#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate ``constraints.txt`` covers direct project dependencies (D08).

Ensures the committed snapshot exists, uses ``name==version`` pins, and
includes every direct runtime + optional-extra requirement from
``pyproject.toml`` (environment markers ignored for coverage checks).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:  # pragma: no cover - py<3.11
    import tomli as tomllib  # type: ignore

PIN_RE = re.compile(r"^([A-Za-z0-9_.\-]+)==([^=]+)$")
REQ_NAME_RE = re.compile(r"^([A-Za-z0-9_.\-]+)")


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_constraints(path: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = PIN_RE.match(line)
        if not match:
            raise ValueError(f"non-pin constraint line: {line}")
        pins[_norm(match.group(1))] = match.group(2)
    return pins


def direct_requirement_names(pyproject: Path) -> set[str]:
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    names: set[str] = set()
    for req in data["project"].get("dependencies", []):
        base = req.split(";", 1)[0].strip()
        match = REQ_NAME_RE.match(base)
        if match:
            names.add(_norm(match.group(1)))
    for extra_reqs in data["project"].get("optional-dependencies", {}).values():
        for req in extra_reqs:
            if req.startswith("codimension["):
                continue
            base = req.split(";", 1)[0].strip()
            match = REQ_NAME_RE.match(base)
            if match:
                names.add(_norm(match.group(1)))
    return names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    constraints = root / "constraints.txt"
    runtime = root / "requirements-runtime.txt"
    errors: list[str] = []
    if not constraints.is_file():
        errors.append("missing constraints.txt — run scripts/generate_constraints.py")
    if not runtime.is_file():
        errors.append("missing requirements-runtime.txt")
    if errors:
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    try:
        pins = parse_constraints(constraints)
    except ValueError as exc:
        print(f"  {exc}", file=sys.stderr)
        return 1
    if len(pins) < 10:
        print(f"  constraints.txt looks too small ({len(pins)} pins)", file=sys.stderr)
        return 1
    required = direct_requirement_names(root / "pyproject.toml")
    # setuptools is often already satisfied by the build env; still expect a pin.
    missing = sorted(name for name in required if name not in pins)
    if missing:
        print("docs check failed: constraints missing direct deps:", file=sys.stderr)
        for name in missing:
            print(f"  {name}", file=sys.stderr)
        return 1
    print(f"constraints OK ({len(pins)} pins; {len(required)} direct deps covered)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
