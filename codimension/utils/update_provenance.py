# -*- coding: utf-8 -*-
#
# codimension - updater provenance + HTTP budgets (R215)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Trusted URL policy and budgeted HTTP reads for the in-app updater (R215).

Integrity (SHA-256) alone does not prove provenance: a hostile mirror that
serves both the artifact and its checksum passes digest checks. This module
fail-closes on cleartext / untrusted hosts and caps response sizes so release
JSON, sidecars, and artifacts cannot exhaust memory.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any, Literal, Mapping, Optional
from urllib.parse import urlparse
from urllib.request import Request, urlopen

#: Default GitHub owner/repo for this fork (API path must match).
DEFAULT_OWNER_REPO = "sesquicadaver/codimension"

#: Env override for expected ``owner/repo`` path segment under ``/repos/``.
OWNER_REPO_ENV = "CDM_UPDATE_OWNER_REPO"

#: Extra comma-separated trusted hosts (API and/or download).
TRUSTED_HOSTS_ENV = "CDM_UPDATE_TRUSTED_HOSTS"

#: Optional override for artifact byte budget.
MAX_ARTIFACT_BYTES_ENV = "CDM_UPDATE_MAX_BYTES"

#: Hosts allowed for the Releases API JSON.
TRUSTED_API_HOSTS: frozenset[str] = frozenset({"api.github.com"})

#: Hosts allowed for release assets / checksum sidecars.
TRUSTED_DOWNLOAD_HOSTS: frozenset[str] = frozenset(
    {
        "github.com",
        "objects.githubusercontent.com",
        "release-assets.githubusercontent.com",
    }
)

DEFAULT_TIMEOUT = 10
MAX_RELEASES_JSON_BYTES = 2 * 1024 * 1024
MAX_CHECKSUM_BYTES = 64 * 1024
DEFAULT_MAX_ARTIFACT_BYTES = 256 * 1024 * 1024
_READ_CHUNK_BYTES = 64 * 1024

UrlPurpose = Literal["releases_api", "download", "checksum"]


class UpdateProvenanceError(ValueError):
    """Raised when an update URL or response violates provenance / budget policy."""


def _host_key(netloc: str) -> str:
    """Normalize ``netloc`` to a lowercase host (strip userinfo / port / brackets)."""
    host = (netloc or "").strip().lower()
    if "@" in host:
        host = host.rsplit("@", 1)[-1]
    if host.startswith("["):
        end = host.find("]")
        if end != -1:
            return host[: end + 1]
        return host
    if ":" in host:
        host = host.rsplit(":", 1)[0]
    return host


def _parse_host_entries(raw: str | None) -> set[str]:
    hosts: set[str] = set()
    for part in (raw or "").split(","):
        item = part.strip()
        if not item:
            continue
        if "://" in item:
            parsed = urlparse(item)
            key = _host_key(parsed.netloc)
            if key:
                hosts.add(key)
            continue
        hosts.add(_host_key(item))
    return {h for h in hosts if h}


def resolve_owner_repo(environ: Optional[Mapping[str, str]] = None) -> str:
    """Return ``owner/repo`` expected in Releases API paths."""
    env: Mapping[str, str] = os.environ if environ is None else environ
    raw = str(env.get(OWNER_REPO_ENV, "")).strip()
    if raw:
        if raw.count("/") != 1:
            raise UpdateProvenanceError(f"{OWNER_REPO_ENV} must be owner/repo, got {raw!r}")
        return raw
    return DEFAULT_OWNER_REPO


def trusted_hosts(
    purpose: UrlPurpose,
    *,
    environ: Optional[Mapping[str, str]] = None,
) -> set[str]:
    """Trusted hosts for ``purpose``, plus optional ``CDM_UPDATE_TRUSTED_HOSTS``."""
    env: Mapping[str, str] = os.environ if environ is None else environ
    if purpose == "releases_api":
        hosts = set(TRUSTED_API_HOSTS)
    else:
        hosts = set(TRUSTED_DOWNLOAD_HOSTS)
    hosts |= _parse_host_entries(env.get(TRUSTED_HOSTS_ENV))
    return hosts


def max_artifact_bytes(environ: Optional[Mapping[str, str]] = None) -> int:
    """Artifact download byte budget (default 256 MiB)."""
    env: Mapping[str, str] = os.environ if environ is None else environ
    raw = str(env.get(MAX_ARTIFACT_BYTES_ENV, "")).strip()
    if not raw:
        return DEFAULT_MAX_ARTIFACT_BYTES
    try:
        value = int(raw)
    except ValueError as exc:
        raise UpdateProvenanceError(f"{MAX_ARTIFACT_BYTES_ENV} must be an integer") from exc
    if value <= 0:
        raise UpdateProvenanceError(f"{MAX_ARTIFACT_BYTES_ENV} must be > 0")
    return value


def assert_trusted_update_url(
    url: str,
    *,
    purpose: UrlPurpose,
    environ: Optional[Mapping[str, str]] = None,
) -> str:
    """Fail closed unless ``url`` is HTTPS on a trusted host (and API path matches)."""
    text = (url or "").strip()
    if not text:
        raise UpdateProvenanceError("update URL is empty")
    parsed = urlparse(text)
    scheme = (parsed.scheme or "").lower()
    host = _host_key(parsed.netloc)
    if scheme != "https" or not host:
        raise UpdateProvenanceError(f"update URL must be absolute https with a host: {text!r}")
    allowed = trusted_hosts(purpose, environ=environ)
    if host not in allowed:
        raise UpdateProvenanceError(f"update URL host {host!r} is not trusted for {purpose}")
    if purpose == "releases_api":
        owner_repo = resolve_owner_repo(environ)
        required = f"/repos/{owner_repo}/releases"
        path = parsed.path or ""
        if path != required and not path.startswith(required + "/"):
            raise UpdateProvenanceError(f"Releases API path must be under {required!r}, got {path!r}")
    return text


def read_budgeted(
    response: Any,
    *,
    max_bytes: int,
    chunk_size: int = _READ_CHUNK_BYTES,
) -> bytes:
    """Read an HTTP response body in chunks; refuse bodies larger than ``max_bytes``."""
    if max_bytes <= 0:
        raise UpdateProvenanceError("response byte budget must be positive")
    chunks: list[bytes] = []
    total = 0
    while True:
        try:
            piece = response.read(chunk_size)
        except TypeError:
            piece = response.read()
            if not isinstance(piece, (bytes, bytearray)):
                piece = bytes(piece)
            if len(piece) > max_bytes:
                raise UpdateProvenanceError(f"update response exceeds {max_bytes} byte budget") from None
            return bytes(piece)
        if not piece:
            break
        if not isinstance(piece, (bytes, bytearray)):
            piece = bytes(piece)
        total += len(piece)
        if total > max_bytes:
            raise UpdateProvenanceError(f"update response exceeds {max_bytes} byte budget")
        chunks.append(bytes(piece))
    return b"".join(chunks)


def sha256_file(path: str, *, max_bytes: Optional[int] = None) -> str:
    """Stream-hash a file; optionally refuse files larger than ``max_bytes``."""
    digest = hashlib.sha256()
    total = 0
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(_READ_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if max_bytes is not None and total > max_bytes:
                raise UpdateProvenanceError(f"artifact exceeds {max_bytes} byte budget while hashing")
            digest.update(chunk)
    return digest.hexdigest()


def stream_url_to_file(
    url: str,
    dest_path: str,
    *,
    max_bytes: int,
    purpose: UrlPurpose = "download",
    timeout: float = DEFAULT_TIMEOUT,
    environ: Optional[Mapping[str, str]] = None,
    user_agent: str = "codimension-update/r215",
) -> str:
    """Download ``url`` to ``dest_path`` with host policy + size cap; return SHA-256 hex."""
    trusted = assert_trusted_update_url(url, purpose=purpose, environ=environ)
    if max_bytes <= 0:
        raise UpdateProvenanceError("artifact byte budget must be positive")
    req = Request(
        trusted,
        headers={
            "Accept": "*/*",
            "User-Agent": user_agent,
        },
        method="GET",
    )
    digest = hashlib.sha256()
    total = 0
    with urlopen(req, timeout=timeout) as resp:
        with open(dest_path, "wb") as handle:
            while True:
                piece = resp.read(_READ_CHUNK_BYTES)
                if not piece:
                    break
                if not isinstance(piece, (bytes, bytearray)):
                    piece = bytes(piece)
                total += len(piece)
                if total > max_bytes:
                    raise UpdateProvenanceError(f"update response exceeds {max_bytes} byte budget")
                digest.update(piece)
                handle.write(piece)
    if total == 0:
        raise UpdateProvenanceError("downloaded artifact is empty")
    return digest.hexdigest()


def fetch_budgeted(
    url: str,
    *,
    purpose: UrlPurpose,
    max_bytes: int,
    timeout: float = DEFAULT_TIMEOUT,
    environ: Optional[Mapping[str, str]] = None,
    user_agent: str = "codimension-update/r215",
    accept: str = "*/*",
    extra_headers: Optional[Mapping[str, str]] = None,
) -> bytes:
    """HTTPS GET with provenance checks and a hard response byte budget."""
    trusted = assert_trusted_update_url(url, purpose=purpose, environ=environ)
    headers = {
        "Accept": accept,
        "User-Agent": user_agent,
    }
    if extra_headers:
        headers.update(dict(extra_headers))
    req = Request(trusted, headers=headers, method="GET")
    with urlopen(req, timeout=timeout) as resp:
        return read_budgeted(resp, max_bytes=max_bytes)


def enforce_declared_size(declared_size: int, *, max_bytes: int, label: str) -> None:
    """Refuse downloads whose declared size already exceeds the budget."""
    if declared_size and declared_size > max_bytes:
        raise UpdateProvenanceError(f"{label} declared size {declared_size} exceeds budget {max_bytes}")


def enforce_payload_budget(payload: bytes, *, max_bytes: int, label: str) -> bytes:
    """Fail closed when an injected/fetched payload exceeds ``max_bytes``."""
    if len(payload) > max_bytes:
        raise UpdateProvenanceError(f"{label} exceeds {max_bytes} byte budget")
    return payload


__all__ = [
    "DEFAULT_MAX_ARTIFACT_BYTES",
    "DEFAULT_OWNER_REPO",
    "DEFAULT_TIMEOUT",
    "MAX_ARTIFACT_BYTES_ENV",
    "MAX_CHECKSUM_BYTES",
    "MAX_RELEASES_JSON_BYTES",
    "OWNER_REPO_ENV",
    "TRUSTED_API_HOSTS",
    "TRUSTED_DOWNLOAD_HOSTS",
    "TRUSTED_HOSTS_ENV",
    "UpdateProvenanceError",
    "UrlPurpose",
    "assert_trusted_update_url",
    "enforce_declared_size",
    "enforce_payload_budget",
    "fetch_budgeted",
    "max_artifact_bytes",
    "read_budgeted",
    "resolve_owner_repo",
    "sha256_file",
    "stream_url_to_file",
    "trusted_hosts",
]
