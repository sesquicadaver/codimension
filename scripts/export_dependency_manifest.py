#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Export a DependencyManifest for a project directory (R120).

Examples::

    python scripts/export_dependency_manifest.py /path/to/project
    python scripts/export_dependency_manifest.py /path/to/project --write
    python scripts/export_dependency_manifest.py /path/to/project --write out-req.txt

Without ``--write``, prints lock hint and unresolved packages to stdout.
With ``--write``, writes unresolved packages to ``requirements.txt`` (or PATH).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODIM = ROOT / "codimension"
for path in (str(ROOT), str(CODIM)):
    if path not in sys.path:
        sys.path.insert(0, path)


def main(argv: list[str] | None = None) -> int:
    """CLI entry: build manifest and optionally write requirements."""
    parser = argparse.ArgumentParser(description="Export DependencyManifest / requirements hint (R120)")
    parser.add_argument("project_dir", type=str, help="Project root directory")
    parser.add_argument(
        "--write",
        nargs="?",
        const="requirements.txt",
        metavar="PATH",
        help="Write unresolved packages to PATH (default: requirements.txt under project)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON (as_dict + lock_hint)",
    )
    parser.add_argument(
        "--packages",
        nargs="*",
        default=None,
        help="Skip import scan; use these package names instead",
    )
    args = parser.parse_args(argv)

    project_dir = os.path.abspath(args.project_dir)
    if not os.path.isdir(project_dir):
        print(f"error: not a directory: {project_dir}", file=sys.stderr)
        return 2

    # Ensure AST parser shims are available for a live unresolved scan.
    try:
        import parsers  # noqa: F401
    except Exception:
        pass

    from utils.dependency_manifest import buildDependencyManifestFromDir

    manifest = buildDependencyManifestFromDir(
        project_dir,
        unresolved_packages=args.packages,
    )

    if args.json:
        payload = manifest.as_dict()
        payload["lock_hint"] = manifest.lock_hint()
        payload["project_dir"] = manifest.project_dir
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        hint = manifest.lock_hint()
        print(f"project_dir: {manifest.project_dir}")
        print(f"requirement_files: {len(manifest.requirement_files)}")
        print(f"has_pyproject: {manifest.has_pyproject}")
        print(f"unresolved_packages: {', '.join(manifest.unresolved_packages) or '(none)'}")
        print(f"lock_hint: {hint or '(none)'}")

    if args.write is not None:
        out = args.write
        if not os.path.isabs(out):
            out = os.path.join(project_dir, out)
        written = manifest.write_requirements(out, mode="w")
        print(f"wrote {written} package(s) to {out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
