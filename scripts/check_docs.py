#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check relative Markdown links and documentation invariants.

Excludes ``doc/www/**`` (immutable archive). Image assets and non-doc code
name references are ignored. Exit code 1 on failures.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
VERSION_RE = re.compile(r'version\s*=\s*"([^"]+)"')
_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico"}


def _skip_raw_target(target: str) -> bool:
    if not target or target.startswith(("#", "mailto:", "http://", "https://")):
        return True
    return False


def _doc_link_path(raw: str) -> str | None:
    """Return a checkable doc path, or None to skip."""
    text = raw.strip()
    if text.startswith("<") and ">" in text:
        text = text[1 : text.index(">")]
    if ' "' in text:
        text = text.split(' "', 1)[0]
    elif " '" in text:
        text = text.split(" '", 1)[0]
    text = text.split("#", 1)[0].strip()
    if not text or text.startswith("~/"):
        return None
    suffix = Path(text).suffix.lower()
    if suffix in _IMAGE_EXT:
        return None
    if suffix and suffix != ".md":
        return None
    if not suffix:
        return None
    return text


def iter_markdown_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*.md"):
        rel = path.relative_to(root).as_posix()
        if rel.startswith("doc/www/") or ".venv/" in rel:
            continue
        files.append(path)
    return sorted(set(files))


def check_links(root: Path, files: list[Path]) -> list[str]:
    errors: list[str] = []
    root_resolved = root.resolve()
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for _label, target in LINK_RE.findall(text):
            raw = target.strip()
            if _skip_raw_target(raw):
                continue
            file_part = _doc_link_path(raw)
            if not file_part:
                continue
            resolved = (path.parent / file_part).resolve()
            try:
                resolved.relative_to(root_resolved)
            except ValueError:
                continue
            if not resolved.exists():
                rel = path.relative_to(root).as_posix()
                errors.append(f"{rel}: broken link -> {file_part}")
    return errors


def check_invariants(root: Path) -> list[str]:
    errors: list[str] = []
    version_file = root / "codimension" / "cdmverspec.py"
    match = VERSION_RE.search(version_file.read_text(encoding="utf-8"))
    if not match:
        errors.append("cdmverspec.py: version not found")
        return errors
    ver = match.group(1)
    for name in ("README.md", "README.en.md"):
        text = (root / name).read_text(encoding="utf-8")
        if ver not in text:
            errors.append(f"{name}: missing version {ver}")
        # Reject open-ended Python marketing outside badges/URLs.
        for line in text.splitlines():
            if "3.10+" in line and "badge" not in line.lower() and "img.shields.io" not in line:
                errors.append(f"{name}: open '3.10+' claim; use CI range 3.10–3.13")
                break
        if "http://codimension.org" in text:
            errors.append(f"{name}: must not promote external http://codimension.org")
        if "master@" in text:
            errors.append(f"{name}: must not embed audit SHA (master@…)")
    for rel in ("doc/uk/README.md", "doc/en/README.md", "doc/INSTALL.md", "doc/en/INSTALL.md"):
        if not (root / rel).is_file():
            errors.append(f"missing required doc: {rel}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    files = iter_markdown_files(root)
    errors = check_links(root, files) + check_invariants(root)
    if errors:
        print(f"docs check failed ({len(errors)}):", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    print(f"docs check OK ({len(files)} markdown files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
