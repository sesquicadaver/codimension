# -*- coding: utf-8 -*-
#
# codimension - verified update artifact download (R173 / R215)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Download a release artifact into a cache dir and verify SHA-256 (R173 / R215).

Fail closed: no trusted checksum → refuse to keep the file; mismatch → delete
partial/wrong bytes. Writes ``manifest.json`` + ``*.sha256`` for R180 apply.

R215: download / checksum URLs must pass HTTPS host policy; declared
``ReleaseAsset.size`` and streamed bytes are hard-capped; production downloads
stream to disk (no unbounded ``response.read()``).
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import urllib.error
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

from utils.update_check import FetchFn, ReleaseAsset, ReleaseInfo
from utils.update_provenance import (
    MAX_CHECKSUM_BYTES,
    UpdateProvenanceError,
    assert_trusted_update_url,
    enforce_declared_size,
    enforce_payload_budget,
    fetch_budgeted,
    max_artifact_bytes,
    stream_url_to_file,
)

#: Preferred artifact suffixes (first match wins among candidates).
ARTIFACT_SUFFIXES: tuple[str, ...] = (".whl", ".tar.gz", ".tgz", ".zip")

#: Companion checksum file suffixes / names.
CHECKSUM_SUFFIXES: tuple[str, ...] = (".sha256", ".sha256sum")
SHA256SUMS_NAMES: frozenset[str] = frozenset({"SHA256SUMS", "sha256sums", "SHA256SUMS.txt"})

_SHA256_HEX_RE = re.compile(r"\b([0-9a-fA-F]{64})\b")
_DIGEST_RE = re.compile(r"^sha256:([0-9a-fA-F]{64})$", re.IGNORECASE)


@dataclass(frozen=True)
class DownloadResult:
    """Outcome of a verified download attempt."""

    status: str  # "ok" | "error"
    path: Optional[str] = None
    sha256: Optional[str] = None
    artifact_name: Optional[str] = None
    message: str = ""
    error: Optional[str] = None


def default_update_cache_dir(home: Optional[str] = None) -> str:
    """Return ``<config-home>/.codimension3/updates`` (honours ``CDM_HOME``)."""
    from utils.portable_profile import updates_cache_dir

    return str(updates_cache_dir(home=home))


def is_checksum_asset_name(name: str) -> bool:
    """Whether ``name`` looks like a checksum sidecar or sums file."""
    lower = (name or "").strip().lower()
    if not lower:
        return False
    if name.strip() in SHA256SUMS_NAMES or lower in {n.lower() for n in SHA256SUMS_NAMES}:
        return True
    return any(lower.endswith(suf) for suf in CHECKSUM_SUFFIXES)


def is_artifact_asset_name(name: str) -> bool:
    """Whether ``name`` looks like a primary installable artifact."""
    lower = (name or "").strip().lower()
    if not lower or is_checksum_asset_name(name):
        return False
    return any(lower.endswith(suf) for suf in ARTIFACT_SUFFIXES)


def select_primary_artifact(assets: Sequence[ReleaseAsset]) -> Optional[ReleaseAsset]:
    """Pick the best downloadable artifact (wheel > sdist > zip)."""
    candidates = [a for a in assets if is_artifact_asset_name(a.name)]
    if not candidates:
        return None

    def _rank(asset: ReleaseAsset) -> tuple[int, str]:
        lower = asset.name.lower()
        for idx, suf in enumerate(ARTIFACT_SUFFIXES):
            if lower.endswith(suf):
                return (idx, lower)
        return (len(ARTIFACT_SUFFIXES), lower)

    return sorted(candidates, key=_rank)[0]


def sha256_hex(data: bytes) -> str:
    """Return lowercase hex SHA-256 of ``data``."""
    return hashlib.sha256(data).hexdigest()


def expected_sha256_from_digest(digest: Optional[str]) -> Optional[str]:
    """Parse GitHub asset ``digest`` field (``sha256:<hex>``)."""
    if not digest:
        return None
    match = _DIGEST_RE.match(digest.strip())
    if match is None:
        return None
    return match.group(1).lower()


def parse_sha256_sidecar(text: str, artifact_name: str) -> Optional[str]:
    """Extract the hex digest for ``artifact_name`` from a sha256sum-style file.

    Accepts lines like ``<hex>  filename`` / ``<hex> *filename``, or a bare
    64-hex line when the sidecar is named ``artifact.sha256``.
    """
    target = os.path.basename(artifact_name).strip()
    bare: Optional[str] = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _SHA256_HEX_RE.search(line)
        if match is None:
            continue
        hex_digest = match.group(1).lower()
        rest = line[match.end() :].strip().lstrip("*").strip()
        if rest:
            if os.path.basename(rest) == target or rest == target:
                return hex_digest
            continue
        if bare is None:
            bare = hex_digest
    return bare


def find_checksum_asset(artifact: ReleaseAsset, assets: Sequence[ReleaseAsset]) -> Optional[ReleaseAsset]:
    """Locate a checksum sidecar or SHA256SUMS asset for ``artifact``."""
    by_name = {a.name: a for a in assets}
    for suf in CHECKSUM_SUFFIXES:
        sibling = by_name.get(artifact.name + suf)
        if sibling is not None:
            return sibling
    for asset in assets:
        if asset.name in SHA256SUMS_NAMES or asset.name.lower() in {n.lower() for n in SHA256SUMS_NAMES}:
            return asset
    return None


def resolve_expected_sha256(
    artifact: ReleaseAsset,
    assets: Sequence[ReleaseAsset],
    *,
    fetch: Optional[FetchFn] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> Optional[str]:
    """Resolve a trusted SHA-256 for ``artifact`` (API digest or sidecar).

    Digests are only as trustworthy as the Releases API / download hosts that
    provided them (R215 provenance policy). Returns ``None`` when no source
    exists (caller must fail closed).
    """
    from_digest = expected_sha256_from_digest(artifact.digest)
    if from_digest is not None:
        return from_digest

    sidecar = find_checksum_asset(artifact, assets)
    if sidecar is None:
        return None
    try:
        assert_trusted_update_url(
            sidecar.browser_download_url,
            purpose="checksum",
            environ=environ,
        )
        enforce_declared_size(sidecar.size, max_bytes=MAX_CHECKSUM_BYTES, label="checksum asset")
        if fetch is not None:
            raw = enforce_payload_budget(
                fetch(sidecar.browser_download_url),
                max_bytes=MAX_CHECKSUM_BYTES,
                label="checksum sidecar",
            )
        else:
            raw = fetch_budgeted(
                sidecar.browser_download_url,
                purpose="checksum",
                max_bytes=MAX_CHECKSUM_BYTES,
                environ=environ,
                user_agent="codimension-update-download/r215",
            )
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, UpdateProvenanceError):
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return parse_sha256_sidecar(text, artifact.name)


def _safe_unlink(path: str) -> None:
    try:
        if path and os.path.isfile(path):
            os.unlink(path)
    except OSError:
        pass


def download_and_verify(
    release: ReleaseInfo,
    cache_dir: str,
    *,
    fetch: Optional[FetchFn] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> DownloadResult:
    """Download the primary artifact for ``release`` into ``cache_dir`` and verify.

    Fail closed: missing checksum, network errors, provenance violations, or
    digest mismatch leave no kept artifact (partial files are removed).
    """
    artifact = select_primary_artifact(release.assets)
    if artifact is None:
        return DownloadResult(
            status="error",
            message="No downloadable artifact on this release.",
            error="no artifact (.whl/.tar.gz/.zip)",
        )

    try:
        budget = max_artifact_bytes(environ)
        assert_trusted_update_url(
            artifact.browser_download_url,
            purpose="download",
            environ=environ,
        )
        enforce_declared_size(artifact.size, max_bytes=budget, label="artifact")
    except UpdateProvenanceError as exc:
        return DownloadResult(
            status="error",
            artifact_name=artifact.name,
            message="Refusing download: untrusted URL or size budget.",
            error=str(exc),
        )

    expected = resolve_expected_sha256(artifact, release.assets, fetch=fetch, environ=environ)
    if expected is None:
        return DownloadResult(
            status="error",
            artifact_name=artifact.name,
            message="Refusing download: no trusted SHA-256 for the artifact.",
            error="checksum unavailable (fail closed)",
        )

    dest_dir = os.path.join(os.path.normpath(cache_dir), release.tag_name.replace("/", "_"))
    try:
        os.makedirs(dest_dir, mode=0o755, exist_ok=True)
    except OSError as exc:
        return DownloadResult(
            status="error",
            artifact_name=artifact.name,
            message="Cannot create update cache directory.",
            error=str(exc),
        )

    dest_path = os.path.join(dest_dir, os.path.basename(artifact.name))
    tmp_path: Optional[str] = None
    try:
        fd, tmp_path = tempfile.mkstemp(prefix=".cdm-upd-", dir=dest_dir)
        os.close(fd)
        if fetch is not None:
            raw = enforce_payload_budget(
                fetch(artifact.browser_download_url),
                max_bytes=budget,
                label="artifact",
            )
            if not raw:
                _safe_unlink(tmp_path)
                return DownloadResult(
                    status="error",
                    artifact_name=artifact.name,
                    message="Downloaded artifact is empty.",
                    error="empty body",
                )
            actual = sha256_hex(raw)
            with open(tmp_path, "wb") as handle:
                handle.write(raw)
        else:
            actual = stream_url_to_file(
                artifact.browser_download_url,
                tmp_path,
                max_bytes=budget,
                purpose="download",
                environ=environ,
                user_agent="codimension-update-download/r215",
            )
        if actual != expected:
            _safe_unlink(tmp_path)
            return DownloadResult(
                status="error",
                artifact_name=artifact.name,
                sha256=actual,
                message="Checksum mismatch; artifact discarded.",
                error=f"expected {expected}, got {actual}",
            )
        os.replace(tmp_path, dest_path)
        tmp_path = None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, UpdateProvenanceError) as exc:
        if tmp_path is not None:
            _safe_unlink(tmp_path)
        _safe_unlink(dest_path)
        return DownloadResult(
            status="error",
            artifact_name=artifact.name,
            message="Network, provenance, or I/O error during download.",
            error=str(exc),
        )
    finally:
        if tmp_path is not None:
            _safe_unlink(tmp_path)

    try:
        from utils.update_apply import write_cache_manifest

        write_cache_manifest(
            dest_dir,
            artifact_path=dest_path,
            sha256=expected,
            tag_name=release.tag_name,
            version=release.version,
            artifact_name=artifact.name,
        )
    except Exception as exc:
        _safe_unlink(dest_path)
        return DownloadResult(
            status="error",
            artifact_name=artifact.name,
            message="Verified bytes but failed to write cache manifest.",
            error=str(exc),
        )

    return DownloadResult(
        status="ok",
        path=dest_path,
        sha256=expected,
        artifact_name=artifact.name,
        message=f"Verified {artifact.name} → {dest_path}",
    )


__all__ = [
    "ARTIFACT_SUFFIXES",
    "CHECKSUM_SUFFIXES",
    "DownloadResult",
    "SHA256SUMS_NAMES",
    "default_update_cache_dir",
    "download_and_verify",
    "expected_sha256_from_digest",
    "find_checksum_asset",
    "is_artifact_asset_name",
    "is_checksum_asset_name",
    "parse_sha256_sidecar",
    "resolve_expected_sha256",
    "select_primary_artifact",
    "sha256_hex",
]
