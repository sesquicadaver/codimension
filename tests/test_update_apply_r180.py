# -*- coding: utf-8 -*-
"""R180: apply verified update from cache + rollback (no network)."""

from __future__ import annotations

import json
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


def _artifact(tmp_path: Path, name: str = "pkg-4.12.0-py3-none-any.whl", payload: bytes = b"wheel-bytes"):
    from utils.update_apply import VerifiedArtifact, write_cache_manifest
    from utils.update_download import sha256_hex

    tag_dir = tmp_path / "updates" / "v4.12.0"
    tag_dir.mkdir(parents=True)
    path = tag_dir / name
    path.write_bytes(payload)
    digest = sha256_hex(payload)
    write_cache_manifest(
        str(tag_dir),
        artifact_path=str(path),
        sha256=digest,
        tag_name="v4.12.0",
        version="4.12.0",
        artifact_name=name,
    )
    return VerifiedArtifact(
        path=str(path),
        sha256=digest,
        tag_name="v4.12.0",
        version="4.12.0",
        artifact_name=name,
    )


def test_portable_cdm_home(tmp_path, monkeypatch):
    from utils.portable_profile import CDM_HOME_ENV, config_dir, resolve_config_home, updates_cache_dir
    from utils.update_download import default_update_cache_dir

    monkeypatch.setenv(CDM_HOME_ENV, str(tmp_path))
    assert resolve_config_home() == os.path.realpath(tmp_path)
    assert config_dir().startswith(str(tmp_path))
    assert default_update_cache_dir() == updates_cache_dir()
    assert "updates" in default_update_cache_dir()


def test_reverify_and_load_manifest(tmp_path):
    from utils.update_apply import load_verified_artifact, reverify_file

    art = _artifact(tmp_path)
    assert reverify_file(art.path, art.sha256) == art.sha256
    loaded = load_verified_artifact(str(Path(art.path).parent))
    assert loaded.path == os.path.realpath(art.path)
    assert loaded.sha256 == art.sha256
    assert loaded.version == "4.12.0"


def test_reverify_fail_closed_mismatch(tmp_path):
    from utils.update_apply import reverify_file

    art = _artifact(tmp_path)
    with pytest.raises(ValueError, match="checksum mismatch"):
        reverify_file(art.path, "a" * 64)


def test_build_pip_install_argv(tmp_path):
    from utils.update_apply import build_pip_install_argv

    art = _artifact(tmp_path)
    argv = build_pip_install_argv("/usr/bin/python3", art.path)
    assert argv[:4] == ["/usr/bin/python3", "-m", "pip", "install"]
    assert "--upgrade" in argv
    assert argv[-1] == os.path.realpath(art.path)


def test_apply_ok_with_fake_install(tmp_path):
    from utils.update_apply import apply_from_cache

    art = _artifact(tmp_path)
    installed: list[str] = []

    def fake_install(argv):
        installed.append(list(argv)[-1])

    result = apply_from_cache(
        art,
        target_python="python3",
        install=fake_install,
        probe_version=lambda _p: "4.12.0",
        state_path=str(tmp_path / "apply-state.json"),
        expect_version="4.12.0",
        home=str(tmp_path),
    )
    assert result.status == "ok"
    assert result.installed_version == "4.12.0"
    assert installed == [os.path.realpath(art.path)]
    state = json.loads((tmp_path / "apply-state.json").read_text(encoding="utf-8"))
    assert state["status"] == "ok"
    assert state["current"]["sha256"] == art.sha256


def test_apply_rolls_back_on_install_failure(tmp_path):
    from utils.update_apply import VerifiedArtifact, apply_from_cache, write_cache_manifest
    from utils.update_download import sha256_hex

    prev_payload = b"previous-wheel"
    prev_dir = tmp_path / "updates" / "v4.11.0"
    prev_dir.mkdir(parents=True)
    prev_path = prev_dir / "pkg-4.11.0-py3-none-any.whl"
    prev_path.write_bytes(prev_payload)
    prev_sha = sha256_hex(prev_payload)
    write_cache_manifest(
        str(prev_dir),
        artifact_path=str(prev_path),
        sha256=prev_sha,
        tag_name="v4.11.0",
        version="4.11.0",
        artifact_name=prev_path.name,
    )
    previous = VerifiedArtifact(
        path=str(prev_path),
        sha256=prev_sha,
        tag_name="v4.11.0",
        version="4.11.0",
        artifact_name=prev_path.name,
    )
    # Seed apply-state with current=previous so next apply can roll back.
    state_file = tmp_path / "apply-state.json"
    state_file.write_text(
        json.dumps({"current": previous.__dict__, "previous": None, "status": "ok"}, indent=2),
        encoding="utf-8",
    )

    new = _artifact(tmp_path, payload=b"new-wheel")
    calls: list[str] = []

    def fake_install(argv):
        path = list(argv)[-1]
        calls.append(path)
        if path == os.path.realpath(new.path):
            raise RuntimeError("pip boom")

    result = apply_from_cache(
        new,
        target_python="python3",
        install=fake_install,
        probe_version=lambda _p: "4.11.0",
        state_path=str(state_file),
        home=str(tmp_path),
    )
    assert result.status == "rolled_back"
    assert calls[0] == os.path.realpath(new.path)
    assert calls[1] == os.path.realpath(previous.path)
    assert result.previous_path == previous.path


def test_apply_refuse_without_sha(tmp_path):
    from utils.update_apply import VerifiedArtifact, apply_from_cache

    path = tmp_path / "x.whl"
    path.write_bytes(b"x")
    art = VerifiedArtifact(path=str(path), sha256="", artifact_name="x.whl")
    result = apply_from_cache(
        art,
        target_python="python3",
        install=lambda _a: None,
        probe_version=lambda _p: "1",
        state_path=str(tmp_path / "st.json"),
    )
    assert result.status == "error"
    assert result.error is not None
    assert "fail closed" in result.error or "SHA-256" in result.error or "required" in result.error


def test_download_writes_manifest(tmp_path):
    from utils.update_check import ReleaseAsset, ReleaseInfo
    from utils.update_download import download_and_verify, sha256_hex

    payload = b"manifested-wheel"
    digest = "sha256:" + sha256_hex(payload)
    release = ReleaseInfo(
        "v4.12.0",
        "4.12.0",
        False,
        "https://example/r",
        assets=(ReleaseAsset("pkg.whl", "https://example/w", 1, digest=digest),),
    )
    result = download_and_verify(release, str(tmp_path), fetch=lambda _u: payload)
    assert result.status == "ok"
    assert result.path is not None
    manifest = Path(result.path).parent / "manifest.json"
    assert manifest.is_file()
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["sha256"] == sha256_hex(payload)
    assert (Path(result.path).parent / (Path(result.path).name + ".sha256")).is_file()


def test_rollback_last_apply(tmp_path):
    from utils.update_apply import VerifiedArtifact, rollback_last_apply
    from utils.update_download import sha256_hex

    payload = b"prev"
    path = tmp_path / "prev.whl"
    path.write_bytes(payload)
    sha = sha256_hex(payload)
    prev = VerifiedArtifact(path=str(path), sha256=sha, version="4.11.0", artifact_name="prev.whl")
    state = tmp_path / "apply-state.json"
    state.write_text(
        json.dumps(
            {
                "current": {"path": str(tmp_path / "gone.whl"), "sha256": "b" * 64},
                "previous": prev.__dict__,
                "status": "ok",
            }
        ),
        encoding="utf-8",
    )
    installed: list[str] = []

    result = rollback_last_apply(
        target_python="python3",
        install=lambda argv: installed.append(list(argv)[-1]),
        probe_version=lambda _p: "4.11.0",
        state_path=str(state),
    )
    assert result.status == "ok"
    assert installed == [os.path.realpath(path)]
