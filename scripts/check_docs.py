#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check documentation links, bilingual parity, and CI Python matrix.

Coverage (B11):
- relative Markdown / image / directory / extensionless targets
- reference-style and HTML ``href`` links
- heading anchors on ``.md`` targets
- UA/EN index + TODO ↔ Living Spec status consistency
- Python CI matrix derived from ``pyproject.toml`` + ``ci.yml`` (not hardcoded)

Excludes ``doc/www/**`` (immutable archive) and fenced code blocks.
Exit code 1 on failures.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

LINK_RE = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)]+)\)")
IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
REF_LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\[([^\]]*)\]")
REF_DEF_RE = re.compile(r"^\[([^\]]+)\]:\s*(\S+)", re.MULTILINE)
HTML_HREF_RE = re.compile(r"""<a\s+[^>]*href=["']([^"']+)["']""", re.IGNORECASE)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
FENCE_RE = re.compile(r"^```.*?$.*?^```\s*$", re.MULTILINE | re.DOTALL)
VERSION_RE = re.compile(r'version\s*=\s*"([^"]+)"')
CLASSIFIER_PY_RE = re.compile(r'Programming Language :: Python :: (3\.\d+)"')
CI_MATRIX_RE = re.compile(r"python-version:\s*\[([^\]]+)\]")
_CODE_EXT = {
    ".py",
    ".pyi",
    ".cdmp",
    ".yml",
    ".yaml",
    ".toml",
    ".json",
    ".sh",
    ".bat",
    ".ps1",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".java",
    ".js",
    ".ts",
    ".css",
    ".html",
}


def strip_fences(text: str) -> str:
    """Remove fenced code blocks so example links are not validated."""
    return FENCE_RE.sub("", text)


def _skip_raw_target(target: str) -> bool:
    if not target or target.startswith(("#", "mailto:", "http://", "https://")):
        return True
    return False


def _normalize_target(raw: str) -> str:
    text = raw.strip()
    if text.startswith("<") and ">" in text:
        text = text[1 : text.index(">")]
    if ' "' in text:
        text = text.split(' "', 1)[0]
    elif " '" in text:
        text = text.split(" '", 1)[0]
    return text.strip()


def _split_anchor(raw: str) -> tuple[str, str | None]:
    text = _normalize_target(raw)
    if "#" in text:
        path, anchor = text.split("#", 1)
        return path.strip(), anchor.strip() or None
    return text, None


def github_slug(heading: str) -> str:
    """Approximate GitHub / commonmark heading slug."""
    text = heading.strip().lower()
    text = re.sub(r"[^\w\s\-]", "", text, flags=re.UNICODE)
    text = re.sub(r"\s+", "-", text.strip())
    return text


def heading_slugs(md_text: str) -> set[str]:
    """Collect heading anchors from markdown (ATX only)."""
    slugs: set[str] = set()
    for _hashes, title in HEADING_RE.findall(strip_fences(md_text)):
        explicit = re.search(r"\{#([^}]+)\}\s*$", title)
        if explicit:
            slugs.add(explicit.group(1))
            title = title[: explicit.start()].strip()
        slug = github_slug(title)
        if slug:
            slugs.add(slug)
    return slugs


def iter_markdown_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*.md"):
        rel = path.relative_to(root).as_posix()
        if rel.startswith("doc/www/") or ".venv/" in rel or rel.startswith(".omx/"):
            continue
        files.append(path)
    return sorted(set(files))


def _should_check_path(file_part: str) -> bool:
    if not file_part or file_part.startswith("~/"):
        return False
    suffix = Path(file_part).suffix.lower()
    if suffix in _CODE_EXT:
        return False
    return True


def collect_link_targets(text: str) -> list[str]:
    """Return raw link/image/href targets from markdown (fences stripped)."""
    body = strip_fences(text)
    targets: list[str] = []
    for _label, target in LINK_RE.findall(body):
        targets.append(target)
    for _label, target in IMG_RE.findall(body):
        targets.append(target)
    for _label, target in HTML_HREF_RE.findall(body):
        targets.append(target)
    defs = {name.lower(): dest for name, dest in REF_DEF_RE.findall(body)}
    for label, ref in REF_LINK_RE.findall(body):
        key = (ref or label).strip().lower()
        if key in defs:
            targets.append(defs[key])
        else:
            targets.append(f"__missing_ref__:{key}")
    return targets


def check_links(root: Path, files: list[Path]) -> list[str]:
    """Validate relative filesystem targets and in-doc anchors."""
    errors: list[str] = []
    root_resolved = root.resolve()
    slug_cache: dict[Path, set[str]] = {}
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for raw in collect_link_targets(text):
            if raw.startswith("__missing_ref__:"):
                key = raw.split(":", 1)[1]
                rel = path.relative_to(root).as_posix()
                errors.append(f"{rel}: missing reference-style definition [{key}]")
                continue
            if _skip_raw_target(raw.strip()):
                continue
            file_part, anchor = _split_anchor(raw)
            if not file_part:
                if not anchor:
                    continue
                if path not in slug_cache:
                    slug_cache[path] = heading_slugs(text)
                if github_slug(anchor) not in slug_cache[path] and anchor not in slug_cache[path]:
                    rel = path.relative_to(root).as_posix()
                    errors.append(f"{rel}: broken anchor -> #{anchor}")
                continue
            if not _should_check_path(file_part):
                continue
            resolved = (path.parent / file_part).resolve()
            try:
                resolved.relative_to(root_resolved)
            except ValueError:
                continue
            if not resolved.exists():
                rel = path.relative_to(root).as_posix()
                errors.append(f"{rel}: broken link -> {file_part}")
                continue
            if anchor and resolved.suffix.lower() == ".md" and resolved.is_file():
                if resolved not in slug_cache:
                    slug_cache[resolved] = heading_slugs(resolved.read_text(encoding="utf-8", errors="replace"))
                slugs = slug_cache[resolved]
                if github_slug(anchor) not in slugs and anchor not in slugs:
                    rel = path.relative_to(root).as_posix()
                    errors.append(f"{rel}: broken anchor -> {file_part}#{anchor}")
    return errors


def parse_ci_python_matrix(ci_text: str) -> list[str]:
    """Return sorted unique Python versions from CI matrix lists."""
    versions: set[str] = set()
    for block in CI_MATRIX_RE.findall(ci_text):
        for part in block.split(","):
            ver = part.strip().strip("\"'")
            if re.fullmatch(r"3\.\d+", ver):
                versions.add(ver)
    return sorted(versions, key=lambda v: tuple(int(x) for x in v.split(".")))


def parse_pyproject_python_classifiers(text: str) -> list[str]:
    """Return Python 3.x classifiers from pyproject.toml."""
    versions = CLASSIFIER_PY_RE.findall(text)
    return sorted(set(versions), key=lambda v: tuple(int(x) for x in v.split(".")))


def format_ci_range(versions: list[str]) -> str:
    """Human range label used in docs (en-dash)."""
    if not versions:
        return ""
    if len(versions) == 1:
        return versions[0]
    return f"{versions[0]}–{versions[-1]}"


def audit_id_statuses(text: str) -> dict[str, str]:
    """Map audit IDs (B11, D07, …) to normalized status from markdown tables."""
    statuses: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        id_cell, *rest = cells
        if id_cell.lower() in {"id", "----", "---"} or set(id_cell) <= {"-", ":"}:
            continue
        status_cell = rest[-1] if rest else ""
        ids = re.findall(r"[BCDEFG]\d{2}", id_cell)
        if not ids:
            continue
        upper = status_cell.upper()
        if "OPEN" in upper or "🔓" in status_cell or "PARTIAL" in upper:
            norm = "OPEN" if "PARTIAL" not in upper else "PARTIAL"
        elif "✅" in status_cell or "CLOSED" in upper or "DONE" in upper:
            norm = "CLOSED"
        else:
            continue
        for audit_id in ids:
            statuses[audit_id] = norm
    return statuses


def check_python_matrix(root: Path) -> list[str]:
    """Ensure docs Python range matches CI matrix and pyproject classifiers."""
    errors: list[str] = []
    ci = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    ci_versions = parse_ci_python_matrix(ci)
    class_versions = parse_pyproject_python_classifiers(pyproject)
    if not ci_versions:
        errors.append("ci.yml: no python-version matrix list found")
        return errors
    if class_versions and class_versions != ci_versions:
        errors.append(f"pyproject classifiers {class_versions} != CI matrix {ci_versions}")
    ci_range = format_ci_range(ci_versions)
    for rel in (
        "README.md",
        "README.en.md",
        "doc/README.md",
        "doc/uk/README.md",
        "doc/en/README.md",
        "doc/INSTALL.md",
        "doc/en/INSTALL.md",
    ):
        path = root / rel
        if not path.is_file():
            errors.append(f"missing required doc: {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        # Accept en-dash or hyphen range forms.
        ok = (
            ci_range in text
            or ci_range.replace("–", "-") in text
            or (", ".join(ci_versions) in text)
            or (" ".join(ci_versions) in text)
        )
        if not ok:
            errors.append(f"{rel}: missing CI Python range {ci_range}")
        for line in text.splitlines():
            if "3.10+" in line and "badge" not in line.lower() and "img.shields.io" not in line:
                # Metadata requires-python may mention >=3.10; reject open marketing.
                if "requires-python" in line or "`>=3.10`" in line or ">=3.10" in line:
                    continue
                errors.append(f"{rel}: open '3.10+' claim; use CI range {ci_range}")
                break
    return errors


def check_bilingual_and_audit(root: Path) -> list[str]:
    """UA/EN index parity markers and TODO ↔ Living Spec status alignment."""
    errors: list[str] = []
    uk = (root / "doc/uk/README.md").read_text(encoding="utf-8")
    en = (root / "doc/en/README.md").read_text(encoding="utf-8")
    for marker in ("3.10–3.13", "sesquicadaver/codimension"):
        if marker not in uk and marker.replace("–", "-") not in uk:
            errors.append(f"doc/uk/README.md: missing parity marker {marker}")
        if marker not in en and marker.replace("–", "-") not in en:
            errors.append(f"doc/en/README.md: missing parity marker {marker}")
    # Platform honesty: uk must not claim equal multi-OS install support.
    bad_uk = "Linux / Windows / macOS"
    if bad_uk in uk:
        errors.append("doc/uk/README.md: outdated equal-OS install claim")

    todo_uk = audit_id_statuses((root / "TODO_FIXME.md").read_text(encoding="utf-8"))
    todo_en = audit_id_statuses((root / "TODO_FIXME.en.md").read_text(encoding="utf-8"))
    if todo_uk != todo_en:
        errors.append("TODO_FIXME.md / TODO_FIXME.en.md: audit ID status mismatch")
    living_uk = audit_id_statuses((root / "doc/plugins/living-specification.md").read_text(encoding="utf-8"))
    living_en = audit_id_statuses((root / "doc/en/plugins/living-specification.md").read_text(encoding="utf-8"))
    if living_uk != living_en:
        errors.append("living-specification uk/en: audit ID status mismatch")
    # Shared IDs must agree between TODO and Living Spec.
    for audit_id in sorted(set(todo_uk) & set(living_uk)):
        if todo_uk[audit_id] != living_uk[audit_id]:
            errors.append(f"TODO vs Living Spec: {audit_id} {todo_uk[audit_id]} != {living_uk[audit_id]}")
    return errors


def check_invariants(root: Path) -> list[str]:
    """Version presence and forbidden marketing in root READMEs."""
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
    errors = (
        check_links(root, files) + check_invariants(root) + check_python_matrix(root) + check_bilingual_and_audit(root)
    )
    if errors:
        print(f"docs check failed ({len(errors)}):", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    print(f"docs check OK ({len(files)} markdown files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
