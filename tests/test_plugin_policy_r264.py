# -*- coding: utf-8 -*-
"""R264: plugin package identity — fd-relative walk; symlink dirs fail-closed."""

from __future__ import annotations

import os
from pathlib import Path

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
    init.write_text("from . import helper\nX = 1\n", encoding="utf-8")
    return info, init


def test_r264_symlink_directory_rejected(tmp_path: Path) -> None:
    """Directory symlink is importable by Python but must invalidate identity."""
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    info, _init = _write_min_plugin(plugin)
    external = tmp_path / "external_helper"
    external.mkdir()
    (external / "__init__.py").write_text("SECRET = 1\n", encoding="utf-8")
    os.symlink(external, plugin / "helper")

    identity = capture_plugin_file_identity(
        info_path=str(info),
        module_filepath=str(plugin / "__init__"),
    )
    assert identity.valid is False
    assert "symlink" in identity.invalid_reason.lower()
    assert identity.package_sha256 == ""

    decision = validate_candidate_before_import(
        info_path=str(info),
        module_filepath=str(plugin / "__init__"),
        name="P",
        version="1",
        plugin_path=str(plugin),
        expected_identity=None,
        ide_version="99.0.0",
        require_manifest=False,
    )
    assert decision.ok is False


def test_r264_symlink_dir_cannot_bypass_between_collect_and_import(tmp_path: Path) -> None:
    """Even if collection somehow saw a clean tree, a later dir symlink is denied."""
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    info, _init = _write_min_plugin(plugin)
    helper = plugin / "helper"
    helper.mkdir()
    (helper / "__init__.py").write_text("Y = 1\n", encoding="utf-8")

    expected = capture_plugin_file_identity(
        info_path=str(info),
        module_filepath=str(plugin / "__init__"),
    )
    assert expected.valid is True
    assert expected.package_sha256

    # Replace real helper package with a symlink to attacker-controlled tree.
    for child in helper.iterdir():
        child.unlink()
    helper.rmdir()
    external = tmp_path / "evil"
    external.mkdir()
    (external / "__init__.py").write_text("Y = 999\n", encoding="utf-8")
    os.symlink(external, helper)

    decision = validate_candidate_before_import(
        info_path=str(info),
        module_filepath=str(plugin / "__init__"),
        name="P",
        version="1",
        plugin_path=str(plugin),
        expected_identity=expected,
        ide_version="99.0.0",
        require_manifest=False,
    )
    assert decision.ok is False
    assert "identity invalid" in decision.reason or "symlink" in decision.reason.lower() or "changed" in decision.reason


def test_r264_symlink_py_file_still_rejected(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    info, _init = _write_min_plugin(plugin)
    target = tmp_path / "outside.py"
    target.write_text("Z = 1\n", encoding="utf-8")
    os.symlink(target, plugin / "helper.py")

    identity = capture_plugin_file_identity(
        info_path=str(info),
        module_filepath=str(plugin / "__init__"),
    )
    assert identity.valid is False
    assert "symlink" in identity.invalid_reason.lower()


def test_r264_nested_real_package_still_hashed(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    info, _init = _write_min_plugin(plugin)
    nested = plugin / "helper"
    nested.mkdir()
    (nested / "__init__.py").write_text("Y = 1\n", encoding="utf-8")
    first = capture_plugin_file_identity(
        info_path=str(info),
        module_filepath=str(plugin / "__init__"),
    )
    assert first.valid is True
    (nested / "__init__.py").write_text("Y = 2\n", encoding="utf-8")
    decision = validate_candidate_before_import(
        info_path=str(info),
        module_filepath=str(plugin / "__init__"),
        name="P",
        version="1",
        plugin_path=str(plugin),
        expected_identity=first,
        ide_version="99.0.0",
        require_manifest=False,
    )
    assert decision.ok is False
    assert "changed" in decision.reason
