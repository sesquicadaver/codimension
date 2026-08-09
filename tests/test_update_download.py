# -*- coding: utf-8 -*-
"""R173: verified update artifact download (fail closed; mocked HTTP)."""

from __future__ import annotations

import hashlib
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


def _asset(name: str, url: str, digest: str | None = None):
    from utils.update_check import ReleaseAsset

    return ReleaseAsset(name=name, browser_download_url=url, size=1, digest=digest)


def _release(assets, tag: str = "v4.12.0"):
    from utils.update_check import ReleaseInfo

    return ReleaseInfo(tag, "4.12.0", False, "https://example/rel", assets=tuple(assets))


def test_select_primary_prefers_wheel() -> None:
    from utils.update_download import select_primary_artifact

    assets = [
        _asset("pkg.zip", "https://example/z"),
        _asset("pkg-4.12.0-py3-none-any.whl", "https://example/w"),
        _asset("pkg-4.12.0.tar.gz", "https://example/t"),
    ]
    picked = select_primary_artifact(assets)
    assert picked is not None
    assert picked.name.endswith(".whl")


def test_parse_sha256_sidecar_named_and_bare() -> None:
    from utils.update_download import parse_sha256_sidecar

    hex_d = "a" * 64
    text = f"{hex_d}  pkg-4.12.0-py3-none-any.whl\n"
    assert parse_sha256_sidecar(text, "pkg-4.12.0-py3-none-any.whl") == hex_d
    assert parse_sha256_sidecar(hex_d + "\n", "pkg.whl") == hex_d


def test_fail_closed_without_checksum(tmp_path: Path) -> None:
    from utils.update_download import download_and_verify

    release = _release([_asset("pkg-4.12.0-py3-none-any.whl", "https://example/w")])
    result = download_and_verify(release, str(tmp_path), fetch=lambda _u: b"payload")
    assert result.status == "error"
    assert result.error is not None
    assert "fail closed" in result.error
    assert list(tmp_path.rglob("*.whl")) == []


def test_download_ok_with_api_digest(tmp_path: Path) -> None:
    from utils.update_download import download_and_verify, sha256_hex

    payload = b"codimension-wheel-bytes"
    digest = "sha256:" + sha256_hex(payload)
    release = _release([_asset("pkg-4.12.0-py3-none-any.whl", "https://example/w", digest)])
    result = download_and_verify(release, str(tmp_path), fetch=lambda _u: payload)
    assert result.status == "ok"
    assert result.path is not None
    assert Path(result.path).is_file()
    assert Path(result.path).read_bytes() == payload
    assert result.sha256 == sha256_hex(payload)


def test_download_ok_with_sidecar(tmp_path: Path) -> None:
    from utils.update_download import download_and_verify, sha256_hex

    payload = b"sdist-bytes"
    hex_d = sha256_hex(payload)
    whl = "codimension-4.12.0.tar.gz"
    assets = [
        _asset(whl, "https://example/t"),
        _asset(whl + ".sha256", "https://example/t.sha256"),
    ]
    blobs = {
        "https://example/t": payload,
        "https://example/t.sha256": f"{hex_d}  {whl}\n".encode(),
    }
    result = download_and_verify(_release(assets), str(tmp_path), fetch=lambda u: blobs[u])
    assert result.status == "ok"
    assert result.path is not None
    assert Path(result.path).read_bytes() == payload


def test_checksum_mismatch_discards_file(tmp_path: Path) -> None:
    from utils.update_download import download_and_verify

    release = _release([_asset("pkg-4.12.0-py3-none-any.whl", "https://example/w", "sha256:" + ("b" * 64))])
    result = download_and_verify(release, str(tmp_path), fetch=lambda _u: b"wrong-bytes")
    assert result.status == "error"
    assert result.error is not None
    assert "expected" in result.error
    assert list(tmp_path.rglob("*.whl")) == []


def test_parse_release_assets_attached() -> None:
    from utils.update_check import parse_release_item

    info = parse_release_item(
        {
            "tag_name": "v4.12.0",
            "prerelease": False,
            "draft": False,
            "html_url": "https://example/r",
            "assets": [
                {
                    "name": "pkg.whl",
                    "browser_download_url": "https://example/pkg.whl",
                    "size": 12,
                    "digest": "sha256:" + ("c" * 64),
                }
            ],
        }
    )
    assert info is not None
    assert len(info.assets) == 1
    assert info.assets[0].name == "pkg.whl"
    assert info.assets[0].digest is not None


def test_default_update_cache_dir() -> None:
    from utils.config import CONFIG_DIR
    from utils.update_download import default_update_cache_dir

    path = default_update_cache_dir(home="/tmp/home")
    assert path == os.path.join("/tmp/home", CONFIG_DIR, "updates")


def test_sha256_hex_matches_hashlib() -> None:
    from utils.update_download import sha256_hex

    data = b"abc"
    assert sha256_hex(data) == hashlib.sha256(data).hexdigest()
