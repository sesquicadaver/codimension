# -*- coding: utf-8 -*-
#
# codimension - apply verified update from cache (R180)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Apply a verified update artifact from the local cache (R180).

Flow: re-verify SHA-256 → optional backup of previous verified wheel →
``pip install`` via injectable runner → probe installed version → rollback on
failure. Fail closed: no trusted digest / mismatch / missing file → refuse.
Does not restart the IDE.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence

from utils.portable_profile import updates_cache_dir
from utils.update_download import sha256_hex

InstallFn = Callable[[Sequence[str]], None]
ProbeFn = Callable[[str], str]

APPLY_STATE_FILENAME = "apply-state.json"
MANIFEST_FILENAME = "manifest.json"


@dataclass(frozen=True)
class VerifiedArtifact:
    """A cache artifact that has been (re)verified."""

    path: str
    sha256: str
    tag_name: str = ""
    version: str = ""
    artifact_name: str = ""


@dataclass(frozen=True)
class ApplyResult:
    """Outcome of apply or rollback."""

    status: str  # "ok" | "error" | "rolled_back"
    message: str = ""
    error: Optional[str] = None
    installed_version: Optional[str] = None
    previous_path: Optional[str] = None


def apply_state_path(*, home: Optional[str] = None) -> str:
    """Return path to ``apply-state.json`` under the updates cache."""
    return os.path.join(updates_cache_dir(home=home), APPLY_STATE_FILENAME)


def reverify_file(path: str, expected_sha256: str) -> str:
    """Hash ``path`` and compare to ``expected_sha256`` (fail closed).

    Returns the actual lowercase hex digest on success.
    """
    if not expected_sha256 or len(expected_sha256.strip()) != 64:
        raise ValueError("trusted SHA-256 required (fail closed)")
    expected = expected_sha256.strip().lower()
    if not os.path.isfile(path):
        raise FileNotFoundError(f"artifact missing: {path}")
    with open(path, "rb") as handle:
        actual = str(sha256_hex(handle.read()))
    if actual != expected:
        raise ValueError(f"checksum mismatch: expected {expected}, got {actual}")
    return actual


def load_verified_artifact(
    cache_tag_dir: str,
    *,
    expected_sha256: Optional[str] = None,
) -> VerifiedArtifact:
    """Load ``manifest.json`` (or infer) from a tag cache dir and re-verify."""
    manifest_path = os.path.join(cache_tag_dir, MANIFEST_FILENAME)
    path = ""
    sha = (expected_sha256 or "").strip().lower()
    tag_name = ""
    version = ""
    artifact_name = ""
    if os.path.isfile(manifest_path):
        raw = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("manifest.json must be an object")
        artifact_name = str(raw.get("artifact_name") or "")
        tag_name = str(raw.get("tag_name") or "")
        version = str(raw.get("version") or "")
        sha = str(raw.get("sha256") or sha).strip().lower()
        rel = str(raw.get("path") or artifact_name)
        path = rel if os.path.isabs(rel) else os.path.join(cache_tag_dir, os.path.basename(rel))
    if not path:
        # Fallback: single artifact file in the directory.
        candidates = [
            os.path.join(cache_tag_dir, name)
            for name in os.listdir(cache_tag_dir)
            if name.endswith((".whl", ".tar.gz", ".tgz", ".zip"))
        ]
        if len(candidates) != 1:
            raise FileNotFoundError(f"no unique artifact in {cache_tag_dir}")
        path = candidates[0]
        artifact_name = os.path.basename(path)
    if not sha:
        sidecar = path + ".sha256"
        if os.path.isfile(sidecar):
            text = Path(sidecar).read_text(encoding="utf-8").strip()
            for token in text.replace("*", " ").split():
                if len(token) == 64 and all(c in "0123456789abcdefABCDEF" for c in token):
                    sha = token.lower()
                    break
    if not sha:
        raise ValueError("no trusted SHA-256 for cached artifact (fail closed)")
    reverify_file(path, sha)
    return VerifiedArtifact(
        path=os.path.realpath(path),
        sha256=sha,
        tag_name=tag_name,
        version=version,
        artifact_name=artifact_name or os.path.basename(path),
    )


def build_pip_install_argv(python: str, artifact_path: str, *, upgrade: bool = True) -> list[str]:
    """Build ``python -m pip install [--upgrade] <artifact>`` argv."""
    if not python:
        raise ValueError("target python is required")
    if not artifact_path or not os.path.isfile(artifact_path):
        raise FileNotFoundError(f"artifact missing: {artifact_path}")
    parts = [python, "-m", "pip", "install"]
    if upgrade:
        parts.append("--upgrade")
    parts.append(os.path.realpath(artifact_path))
    return parts


def default_install(argv: Sequence[str]) -> None:
    """Run pip install via subprocess; raise on non-zero exit."""
    completed = subprocess.run(
        list(argv),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip() or f"exit {completed.returncode}"
        raise RuntimeError(f"pip install failed: {err}")


def default_probe_version(python: str) -> str:
    """Return ``cdmverspec.version`` from ``python``."""
    completed = subprocess.run(
        [python, "-c", "import cdmverspec; print(cdmverspec.version)"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"version probe failed: {err}")
    return (completed.stdout or "").strip()


def _load_state(path: str) -> dict:
    if not os.path.isfile(path):
        return {}
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _save_state(path: str, payload: dict) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, mode=0o755, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp = tempfile.mkstemp(prefix=".cdm-apply-", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            if os.path.isfile(tmp):
                os.unlink(tmp)
        except OSError:
            pass
        raise


def _entry_from_artifact(artifact: VerifiedArtifact) -> dict:
    return {
        "path": artifact.path,
        "sha256": artifact.sha256,
        "tag_name": artifact.tag_name,
        "version": artifact.version,
        "artifact_name": artifact.artifact_name,
    }


def _artifact_from_entry(entry: object) -> Optional[VerifiedArtifact]:
    if not isinstance(entry, dict):
        return None
    path = str(entry.get("path") or "")
    sha = str(entry.get("sha256") or "")
    if not path or not sha:
        return None
    return VerifiedArtifact(
        path=path,
        sha256=sha,
        tag_name=str(entry.get("tag_name") or ""),
        version=str(entry.get("version") or ""),
        artifact_name=str(entry.get("artifact_name") or os.path.basename(path)),
    )


def _install_artifact(
    artifact: VerifiedArtifact,
    *,
    target_python: str,
    install: InstallFn,
) -> None:
    reverify_file(artifact.path, artifact.sha256)
    argv = build_pip_install_argv(target_python, artifact.path)
    install(argv)


def apply_from_cache(
    artifact: VerifiedArtifact,
    *,
    target_python: str,
    install: Optional[InstallFn] = None,
    probe_version: Optional[ProbeFn] = None,
    state_path: Optional[str] = None,
    expect_version: Optional[str] = None,
    home: Optional[str] = None,
) -> ApplyResult:
    """Install ``artifact`` into ``target_python`` after re-verify.

    On install/probe failure, attempts rollback to the previous verified
    artifact recorded in apply-state (if any).
    """
    install_fn = install if install is not None else default_install
    probe_fn = probe_version if probe_version is not None else default_probe_version
    state_file = state_path or apply_state_path(home=home)

    try:
        reverify_file(artifact.path, artifact.sha256)
    except (OSError, ValueError) as exc:
        return ApplyResult(status="error", message="Refuse apply: re-verify failed.", error=str(exc))

    state = _load_state(state_file)
    previous = _artifact_from_entry(state.get("current")) or _artifact_from_entry(state.get("previous"))

    # Snapshot current → previous before mutating install.
    new_state = {
        "current": _entry_from_artifact(artifact),
        "previous": _entry_from_artifact(previous) if previous is not None else None,
    }
    try:
        _save_state(state_file, {**new_state, "status": "pending"})
    except OSError as exc:
        return ApplyResult(status="error", message="Cannot write apply-state.", error=str(exc))

    try:
        _install_artifact(artifact, target_python=target_python, install=install_fn)
        installed = probe_fn(target_python)
        if expect_version and installed and installed != expect_version:
            raise RuntimeError(f"installed version {installed!r} != expected {expect_version!r}")
    except Exception as exc:
        logging.error("Update apply failed: %s", exc)
        if previous is not None and os.path.isfile(previous.path):
            try:
                _install_artifact(previous, target_python=target_python, install=install_fn)
                _save_state(
                    state_file,
                    {
                        "current": _entry_from_artifact(previous),
                        "previous": None,
                        "status": "rolled_back",
                        "last_error": str(exc),
                    },
                )
                return ApplyResult(
                    status="rolled_back",
                    message="Apply failed; restored previous verified artifact.",
                    error=str(exc),
                    previous_path=previous.path,
                )
            except Exception as rollback_exc:
                _save_state(
                    state_file,
                    {
                        "current": _entry_from_artifact(previous),
                        "previous": None,
                        "status": "error",
                        "last_error": f"{exc}; rollback failed: {rollback_exc}",
                    },
                )
                return ApplyResult(
                    status="error",
                    message="Apply failed and rollback also failed.",
                    error=f"{exc}; rollback: {rollback_exc}",
                    previous_path=previous.path,
                )
        _save_state(
            state_file,
            {
                "current": None,
                "previous": _entry_from_artifact(previous) if previous else None,
                "status": "error",
                "last_error": str(exc),
            },
        )
        return ApplyResult(status="error", message="Apply failed.", error=str(exc))

    _save_state(state_file, {**new_state, "status": "ok", "installed_version": installed})
    return ApplyResult(
        status="ok",
        message=f"Applied {artifact.artifact_name} → {installed}",
        installed_version=installed,
        previous_path=previous.path if previous else None,
    )


def rollback_last_apply(
    *,
    target_python: str,
    install: Optional[InstallFn] = None,
    probe_version: Optional[ProbeFn] = None,
    state_path: Optional[str] = None,
    home: Optional[str] = None,
) -> ApplyResult:
    """Re-install the previous verified artifact from apply-state."""
    install_fn = install if install is not None else default_install
    probe_fn = probe_version if probe_version is not None else default_probe_version
    state_file = state_path or apply_state_path(home=home)
    state = _load_state(state_file)
    previous = _artifact_from_entry(state.get("previous"))
    if previous is None:
        return ApplyResult(status="error", message="No previous artifact to roll back to.", error="no previous")
    try:
        _install_artifact(previous, target_python=target_python, install=install_fn)
        installed = probe_fn(target_python)
    except Exception as exc:
        return ApplyResult(status="error", message="Rollback failed.", error=str(exc), previous_path=previous.path)
    _save_state(
        state_file,
        {
            "current": _entry_from_artifact(previous),
            "previous": None,
            "status": "rolled_back",
            "installed_version": installed,
        },
    )
    return ApplyResult(
        status="ok",
        message=f"Rolled back to {previous.artifact_name}",
        installed_version=installed,
        previous_path=previous.path,
    )


def write_cache_manifest(
    dest_dir: str,
    *,
    artifact_path: str,
    sha256: str,
    tag_name: str,
    version: str,
    artifact_name: str,
) -> str:
    """Write ``manifest.json`` + ``*.sha256`` sidecar next to the artifact."""
    os.makedirs(dest_dir, mode=0o755, exist_ok=True)
    basename = os.path.basename(artifact_path)
    payload = {
        "tag_name": tag_name,
        "version": version,
        "artifact_name": artifact_name or basename,
        "sha256": sha256.lower(),
        "path": basename,
    }
    manifest_path = os.path.join(dest_dir, MANIFEST_FILENAME)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp = tempfile.mkstemp(prefix=".cdm-manifest-", suffix=".json", dir=dest_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, manifest_path)
    except Exception:
        try:
            if os.path.isfile(tmp):
                os.unlink(tmp)
        except OSError:
            pass
        raise

    sidecar = artifact_path + ".sha256"
    sidecar_body = f"{sha256.lower()}  {basename}\n"
    fd2, tmp2 = tempfile.mkstemp(prefix=".cdm-sha-", suffix=".sha256", dir=dest_dir)
    try:
        with os.fdopen(fd2, "w", encoding="utf-8") as handle:
            handle.write(sidecar_body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp2, sidecar)
    except Exception:
        try:
            if os.path.isfile(tmp2):
                os.unlink(tmp2)
        except OSError:
            pass
        raise
    return manifest_path


def copy_into_rollback_slot(artifact: VerifiedArtifact, *, home: Optional[str] = None) -> str:
    """Copy artifact into ``updates/previous/`` for durable rollback material."""
    slot = os.path.join(updates_cache_dir(home=home), "previous")
    os.makedirs(slot, mode=0o755, exist_ok=True)
    dest = os.path.join(slot, os.path.basename(artifact.path))
    if os.path.realpath(artifact.path) != os.path.realpath(dest):
        shutil.copy2(artifact.path, dest)
    sidecar = dest + ".sha256"
    with open(sidecar, "w", encoding="utf-8") as handle:
        handle.write(f"{artifact.sha256}  {os.path.basename(dest)}\n")
    return dest


__all__ = [
    "APPLY_STATE_FILENAME",
    "ApplyResult",
    "InstallFn",
    "MANIFEST_FILENAME",
    "ProbeFn",
    "VerifiedArtifact",
    "apply_from_cache",
    "apply_state_path",
    "build_pip_install_argv",
    "copy_into_rollback_slot",
    "default_install",
    "default_probe_version",
    "load_verified_artifact",
    "reverify_file",
    "rollback_last_apply",
    "write_cache_manifest",
]
