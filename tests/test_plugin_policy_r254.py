# -*- coding: utf-8 -*-
"""R254: plugin package identity fail-closed for oversized/unreadable members."""

from __future__ import annotations

from pathlib import Path

from plugins import policy
from plugins.policy import capture_plugin_file_identity, validate_candidate_before_import


def _write_min_plugin(root: Path) -> tuple[Path, Path]:
    info = root / "plug.cdmp"
    info.write_text(
        "[Core]\nName = P\nModule = __init__\n"
        "[Codimension]\nCategory = WizardInterface\nMinIDEVersion = 5.0.0\n"
        "MinPluginAPI = 1\nRequiredCapabilities =\nEntrypoint = __init__\n",
        encoding="utf-8",
    )
    init = root / "__init__.py"
    init.write_text("X = 1\n", encoding="utf-8")
    return info, init


def test_r254_oversized_member_invalid_not_stable_empty(tmp_path: Path, monkeypatch) -> None:
    """Oversized helper must not yield two equal empty digests that pass the gate."""
    monkeypatch.setattr(policy, "_MAX_PLUGIN_FILE_BYTES", 64)
    monkeypatch.setattr(policy, "_MAX_PLUGIN_PACKAGE_TOTAL_BYTES", 256)
    info, _init = _write_min_plugin(tmp_path)
    helper = tmp_path / "helper.py"
    helper.write_bytes(b"A" * 128)

    first = capture_plugin_file_identity(info_path=str(info), module_filepath=str(tmp_path / "__init__"))
    assert first.valid is False
    assert first.package_sha256 == ""
    assert "exceeds" in first.invalid_reason

    helper.write_bytes(b"B" * 128)  # still oversized, content changed
    second = capture_plugin_file_identity(info_path=str(info), module_filepath=str(tmp_path / "__init__"))
    assert second.valid is False

    # Pre-R254 bug: empty digests compared equal and import was allowed.
    decision = validate_candidate_before_import(
        info_path=str(info),
        module_filepath=str(tmp_path / "__init__"),
        name="P",
        version="1",
        plugin_path=str(tmp_path),
        expected_identity=first,
        ide_version="99.0.0",
        require_manifest=False,
    )
    assert decision.ok is False
    assert "R254" in decision.reason or "invalid" in decision.reason.lower()


def test_r254_valid_package_still_detects_sibling_change(tmp_path: Path) -> None:
    info, _init = _write_min_plugin(tmp_path)
    sibling = tmp_path / "helper.py"
    sibling.write_text("Y = 1\n", encoding="utf-8")
    expected = capture_plugin_file_identity(info_path=str(info), module_filepath=str(tmp_path / "__init__"))
    assert expected.valid is True
    assert expected.package_sha256
    sibling.write_text("Y = 2\n", encoding="utf-8")
    decision = validate_candidate_before_import(
        info_path=str(info),
        module_filepath=str(tmp_path / "__init__"),
        name="P",
        version="1",
        plugin_path=str(tmp_path),
        expected_identity=expected,
        ide_version="99.0.0",
        require_manifest=False,
    )
    assert decision.ok is False
    assert "changed" in decision.reason


def test_r254_package_file_budget(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(policy, "_MAX_PLUGIN_PACKAGE_FILES", 2)
    info, _init = _write_min_plugin(tmp_path)
    (tmp_path / "a.py").write_text("a=1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("b=1\n", encoding="utf-8")
    # __init__.py + a.py + b.py = 3 files → over budget of 2
    identity = capture_plugin_file_identity(info_path=str(info), module_filepath=str(tmp_path / "__init__"))
    assert identity.valid is False
    assert "py count exceeds" in identity.invalid_reason


def test_r254_package_depth_budget(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(policy, "_MAX_PLUGIN_PACKAGE_DEPTH", 1)
    info, _init = _write_min_plugin(tmp_path)
    nested = tmp_path / "sub" / "deep"
    nested.mkdir(parents=True)
    (nested / "x.py").write_text("x=1\n", encoding="utf-8")
    identity = capture_plugin_file_identity(info_path=str(info), module_filepath=str(tmp_path / "__init__"))
    assert identity.valid is False
    assert "depth exceeds" in identity.invalid_reason


def test_r254_oversized_cdmp_bounded_parse(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(policy, "_MAX_PLUGIN_FILE_BYTES", 32)
    info = tmp_path / "plug.cdmp"
    info.write_text("[Core]\nName = P\n" + ("X = 1\n" * 40), encoding="utf-8")
    (tmp_path / "__init__.py").write_text("X = 1\n", encoding="utf-8")
    core, cdm, err = policy._parse_cdmp_sections(str(info))
    assert core == {} and cdm == {}
    assert "exceeds" in err


def test_r254_current_invalid_denies_without_expected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(policy, "_MAX_PLUGIN_FILE_BYTES", 32)
    info, _init = _write_min_plugin(tmp_path)
    (tmp_path / "helper.py").write_bytes(b"Z" * 64)
    decision = validate_candidate_before_import(
        info_path=str(info),
        module_filepath=str(tmp_path / "__init__"),
        name="P",
        version="1",
        plugin_path=str(tmp_path),
        expected_identity=None,
        ide_version="99.0.0",
        require_manifest=False,
    )
    assert decision.ok is False
    assert "identity invalid" in decision.reason
