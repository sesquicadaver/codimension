# -*- coding: utf-8 -*-
"""R215: updater provenance policy, budgets, and version probe."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import parsers  # noqa: E402,F401
import pytest

_CODIM = Path(__file__).resolve().parents[1] / "codimension"


@pytest.fixture(autouse=True)
def _purge_stubs():
    import importlib

    def _under(mod: object) -> bool:
        path = getattr(mod, "__file__", None)
        if path:
            return "/codimension/" in os.path.abspath(path).replace("\\", "/")
        return False

    dirty = False
    for name in list(sys.modules):
        if name not in ("ui", "utils") and not name.startswith(("ui.", "utils.")):
            continue
        if _under(sys.modules[name]):
            continue
        del sys.modules[name]
        dirty = True
    if dirty:
        importlib.invalidate_caches()
        if str(_CODIM) not in sys.path:
            sys.path.insert(0, str(_CODIM))
    yield


def test_assert_trusted_releases_api_path() -> None:
    from utils.update_provenance import UpdateProvenanceError, assert_trusted_update_url

    ok = assert_trusted_update_url(
        "https://api.github.com/repos/sesquicadaver/codimension/releases",
        purpose="releases_api",
        environ={},
    )
    assert ok.startswith("https://api.github.com/")
    with pytest.raises(UpdateProvenanceError):
        assert_trusted_update_url(
            "http://api.github.com/repos/sesquicadaver/codimension/releases",
            purpose="releases_api",
            environ={},
        )
    with pytest.raises(UpdateProvenanceError):
        assert_trusted_update_url(
            "https://api.github.com/repos/other/repo/releases",
            purpose="releases_api",
            environ={},
        )


def test_trusted_hosts_env_extends_allowlist() -> None:
    from utils.update_provenance import TRUSTED_HOSTS_ENV, assert_trusted_update_url

    url = "https://mirror.example/asset.whl"
    env = {TRUSTED_HOSTS_ENV: "mirror.example"}
    assert assert_trusted_update_url(url, purpose="download", environ=env) == url


def test_read_budgeted_enforces_limit() -> None:
    from utils.update_provenance import UpdateProvenanceError, read_budgeted

    class _Resp:
        def __init__(self, data: bytes) -> None:
            self._data = data
            self._pos = 0

        def read(self, n: int = -1) -> bytes:
            if self._pos >= len(self._data):
                return b""
            if n < 0:
                chunk = self._data[self._pos :]
                self._pos = len(self._data)
                return chunk
            chunk = self._data[self._pos : self._pos + n]
            self._pos += len(chunk)
            return chunk

    assert read_budgeted(_Resp(b"abc"), max_bytes=10) == b"abc"
    with pytest.raises(UpdateProvenanceError):
        read_budgeted(_Resp(b"x" * 100), max_bytes=16)


def test_default_probe_version_uses_metadata(tmp_path: Path) -> None:
    """Probe script prefers importlib.metadata over top-level cdmverspec."""
    from utils.update_apply import _VERSION_PROBE_CODE, default_probe_version

    assert "importlib.metadata" in _VERSION_PROBE_CODE
    assert "cdmverspec" in _VERSION_PROBE_CODE
    # Live probe against the current interpreter (dev layout may use fallback).
    version = default_probe_version(sys.executable)
    assert version
    assert any(ch.isdigit() for ch in version)


def test_sha256_file_streams(tmp_path: Path) -> None:
    from utils.update_provenance import sha256_file

    path = tmp_path / "blob.bin"
    path.write_bytes(b"hello-r215")
    assert sha256_file(str(path)) == __import__("hashlib").sha256(b"hello-r215").hexdigest()
