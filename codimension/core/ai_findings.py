# -*- coding: utf-8 -*-
#
# codimension - structured AI findings (R231)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Structured AI finding model, validation, dedupe, and SARIF-like export (R231).

Findings are evidence-oriented records (severity, confidence, optional spans).
LLM prose is accepted only after deterministic schema validation — invalid
entries are dropped, not silently trusted.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence


class AiFindingSeverity(str, Enum):
    """Finding severity levels (SARIF-aligned names)."""

    ERROR = "error"
    WARNING = "warning"
    NOTE = "note"
    INFO = "info"


_SEVERITY_ALIASES: Mapping[str, AiFindingSeverity] = {
    "error": AiFindingSeverity.ERROR,
    "err": AiFindingSeverity.ERROR,
    "critical": AiFindingSeverity.ERROR,
    "high": AiFindingSeverity.ERROR,
    "warning": AiFindingSeverity.WARNING,
    "warn": AiFindingSeverity.WARNING,
    "medium": AiFindingSeverity.WARNING,
    "note": AiFindingSeverity.NOTE,
    "info": AiFindingSeverity.INFO,
    "informational": AiFindingSeverity.INFO,
    "low": AiFindingSeverity.INFO,
}


@dataclass(frozen=True, slots=True)
class AiFinding:
    """One validated, evidence-backed AI finding."""

    finding_id: str
    severity: AiFindingSeverity
    confidence: float
    title: str
    message: str
    file_path: str = ""
    begin_line: int = 0
    end_line: int = 0
    evidence: str = ""
    rule_id: str = ""

    def __post_init__(self) -> None:
        """Reject out-of-range confidence."""
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence!r}")


@dataclass(frozen=True, slots=True)
class AiFindingsReport:
    """Deduped findings plus budget/accounting metadata for one AI job."""

    findings: tuple[AiFinding, ...]
    tokens_used: int = 0
    cost_usd: float = 0.0
    stopped_by_budget: bool = False
    files_analyzed: int = 0
    files_skipped: int = 0

    def to_markdown(self) -> str:
        """Render a human-readable findings section."""
        lines = [
            f"# Structured findings ({len(self.findings)})",
            "",
            f"- Tokens used (estimate): {self.tokens_used}",
            f"- Cost estimate (USD): {self.cost_usd:.4f}",
            f"- Files analyzed: {self.files_analyzed}",
        ]
        if self.stopped_by_budget:
            lines.append("- Stopped early: global AI budget exhausted")
        if self.files_skipped:
            lines.append(f"- Files skipped (budget): {self.files_skipped}")
        lines.append("")
        if not self.findings:
            lines.append("_No validated findings._")
            return "\n".join(lines)
        for item in self.findings:
            loc = item.file_path or "(unknown file)"
            if item.begin_line > 0:
                loc = f"{loc}:{item.begin_line}"
                if item.end_line > item.begin_line:
                    loc = f"{loc}-{item.end_line}"
            lines.append(f"## [{item.severity.value}] {item.title}")
            lines.append(f"- Id: `{item.finding_id}`")
            if item.rule_id:
                lines.append(f"- Rule: `{item.rule_id}`")
            lines.append(f"- Confidence: {item.confidence:.2f}")
            lines.append(f"- Location: {loc}")
            lines.append(f"- {item.message}")
            if item.evidence:
                lines.append(f"- Evidence: {item.evidence}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"


def _stable_id(*parts: str) -> str:
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def normalize_severity(value: object) -> AiFindingSeverity | None:
    """Map a free-form severity label to :class:`AiFindingSeverity`, or ``None``."""
    if isinstance(value, AiFindingSeverity):
        return value
    key = str(value or "").strip().lower()
    return _SEVERITY_ALIASES.get(key)


def validate_finding_dict(raw: Mapping[str, Any], *, default_file: str = "") -> AiFinding | None:
    """Validate one mapping into an :class:`AiFinding`, or ``None`` if invalid."""
    if not isinstance(raw, Mapping):
        return None
    title = str(raw.get("title") or raw.get("name") or "").strip()
    message = str(raw.get("message") or raw.get("description") or "").strip()
    if not title or not message:
        return None
    severity = normalize_severity(raw.get("severity") or raw.get("level") or "warning")
    if severity is None:
        return None
    try:
        confidence = float(raw.get("confidence", 0.5))
    except (TypeError, ValueError):
        return None
    if not 0.0 <= confidence <= 1.0:
        return None
    file_path = str(raw.get("file_path") or raw.get("file") or default_file or "").strip()
    begin_line = _nonneg_int(raw.get("begin_line", raw.get("line", 0)))
    end_line = _nonneg_int(raw.get("end_line", begin_line))
    if end_line < begin_line:
        end_line = begin_line
    evidence = str(raw.get("evidence") or raw.get("source") or "").strip()
    rule_id = str(raw.get("rule_id") or raw.get("rule") or "").strip()
    finding_id = str(raw.get("finding_id") or raw.get("id") or "").strip()
    if not finding_id:
        finding_id = _stable_id(file_path, str(begin_line), severity.value, title, message[:80])
    try:
        return AiFinding(
            finding_id=finding_id,
            severity=severity,
            confidence=confidence,
            title=title[:200],
            message=message[:4000],
            file_path=file_path,
            begin_line=begin_line,
            end_line=end_line,
            evidence=evidence[:2000],
            rule_id=rule_id[:120],
        )
    except ValueError:
        return None


def _nonneg_int(value: object) -> int:
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        return 0
    return max(0, number)


_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL | re.IGNORECASE)


def extract_json_payload(text: str) -> Any | None:
    """Extract a JSON object/array from prose or a fenced block."""
    raw = (text or "").strip()
    if not raw:
        return None
    candidates: list[str] = [raw]
    match = _JSON_FENCE.search(raw)
    if match:
        candidates.insert(0, match.group(1))
    # Also try first [...] or {...} slice.
    for opener, closer in (("[", "]"), ("{", "}")):
        start = raw.find(opener)
        end = raw.rfind(closer)
        if start != -1 and end > start:
            candidates.append(raw[start : end + 1])
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def parse_findings_payload(text: str, *, default_file: str = "") -> tuple[AiFinding, ...]:
    """Parse and validate findings from an LLM (or tool) response body."""
    payload = extract_json_payload(text)
    if payload is None:
        return ()
    items: list[Any]
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        nested = payload.get("findings")
        if isinstance(nested, list):
            items = nested
        else:
            items = [payload]
    else:
        return ()
    out: list[AiFinding] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        finding = validate_finding_dict(item, default_file=default_file)
        if finding is not None:
            out.append(finding)
    return tuple(out)


def dedupe_findings(findings: Iterable[AiFinding]) -> tuple[AiFinding, ...]:
    """Drop duplicate findings by id, then by (file, lines, title, message)."""
    seen_ids: set[str] = set()
    seen_keys: set[tuple[str, int, int, str, str]] = set()
    out: list[AiFinding] = []
    for item in findings:
        if item.finding_id in seen_ids:
            continue
        key = (item.file_path, item.begin_line, item.end_line, item.title, item.message)
        if key in seen_keys:
            continue
        seen_ids.add(item.finding_id)
        seen_keys.add(key)
        out.append(item)
    return tuple(out)


def findings_to_sarif(report: AiFindingsReport, *, tool_name: str = "codimension-ai") -> dict[str, Any]:
    """Return a minimal SARIF 2.1.0-compatible document for ``report``."""
    results: list[dict[str, Any]] = []
    for item in report.findings:
        physical: dict[str, Any] = {"artifactLocation": {"uri": item.file_path or "about:blank"}}
        if item.begin_line > 0:
            physical["region"] = {
                "startLine": item.begin_line,
                "endLine": item.end_line or item.begin_line,
            }
        results.append(
            {
                "ruleId": item.rule_id or item.finding_id,
                "level": item.severity.value,
                "message": {"text": f"{item.title}: {item.message}"},
                "locations": [{"physicalLocation": physical}],
                "properties": {
                    "confidence": item.confidence,
                    "evidence": item.evidence,
                    "findingId": item.finding_id,
                },
            }
        )
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {"name": tool_name, "informationUri": "https://github.com/sesquicadaver/codimension"}
                },
                "results": results,
                "properties": {
                    "tokensUsed": report.tokens_used,
                    "costUsd": report.cost_usd,
                    "stoppedByBudget": report.stopped_by_budget,
                    "filesAnalyzed": report.files_analyzed,
                    "filesSkipped": report.files_skipped,
                },
            }
        ],
    }


def merge_finding_sequences(*groups: Sequence[AiFinding]) -> tuple[AiFinding, ...]:
    """Concatenate and dedupe finding groups."""
    merged: list[AiFinding] = []
    for group in groups:
        merged.extend(group)
    return dedupe_findings(merged)


__all__ = [
    "AiFinding",
    "AiFindingSeverity",
    "AiFindingsReport",
    "dedupe_findings",
    "extract_json_payload",
    "findings_to_sarif",
    "merge_finding_sequences",
    "normalize_severity",
    "parse_findings_payload",
    "validate_finding_dict",
]
