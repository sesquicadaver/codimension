# -*- coding: utf-8 -*-
"""R225 — third-party plugin .cdmp [Codimension] fail-closed (no legacy import)."""

from __future__ import annotations

import textwrap
from pathlib import Path

from plugins.policy import (
    build_static_plugin_policy,
    evaluate_static_plugin_policy,
)


def test_r225_third_party_comment_category_is_not_enough(tmp_path: Path) -> None:
    """Substring/comment category must not unlock third-party import (P1-07)."""
    src = tmp_path / "__init__.py"
    src.write_text(
        "# VersionControlSystemInterface in a comment must not count\nclass X:\n    pass\n",
        encoding="utf-8",
    )
    info = tmp_path / "p.cdmp"
    info.write_text(
        textwrap.dedent(
            """\
            [Core]
            Name = Fake
            Module = .

            [Documentation]
            Author = t
            Version = 1.0.0
            Description = no Codimension block
            """
        ),
        encoding="utf-8",
    )
    policy = build_static_plugin_policy(
        info_path=str(info),
        module_filepath=str(tmp_path / "__init__"),
        require_manifest=True,
        plugin_path=str(tmp_path),
    )
    decision = evaluate_static_plugin_policy(policy, ide_version="5.0.0")
    assert not decision.ok
    assert "Codimension" in decision.reason


def test_r225_invalid_minpluginapi_denies_candidate(tmp_path: Path) -> None:
    """Bad numeric manifest fields deny this candidate; they must not raise."""
    info = tmp_path / "p.cdmp"
    info.write_text(
        textwrap.dedent(
            """\
            [Core]
            Name = BadInt
            Module = .

            [Codimension]
            Category = WizardInterface
            MinIDEVersion = 4.0.0
            MinPluginAPI = not-an-int
            RequiredCapabilities = wizard
            Entrypoint = .
            """
        ),
        encoding="utf-8",
    )
    (tmp_path / "__init__.py").write_text("class X:\n    pass\n", encoding="utf-8")
    policy = build_static_plugin_policy(
        info_path=str(info),
        module_filepath=str(tmp_path / "__init__"),
        require_manifest=True,
    )
    decision = evaluate_static_plugin_policy(policy, ide_version="5.0.0")
    assert not decision.ok
    assert "MinPluginAPI" in decision.reason


def test_r225_complete_manifest_accepted(tmp_path: Path) -> None:
    info = tmp_path / "p.cdmp"
    info.write_text(
        textwrap.dedent(
            """\
            [Core]
            Name = Ok
            Module = .

            [Codimension]
            Category = WizardInterface
            MinIDEVersion = 4.0.0
            MinPluginAPI = 1
            RequiredCapabilities = wizard
            Entrypoint = .
            """
        ),
        encoding="utf-8",
    )
    (tmp_path / "__init__.py").write_text("class X:\n    pass\n", encoding="utf-8")
    policy = build_static_plugin_policy(
        info_path=str(info),
        module_filepath=str(tmp_path / "__init__"),
        require_manifest=True,
    )
    decision = evaluate_static_plugin_policy(policy, ide_version="5.0.0")
    assert decision.ok
    assert policy.capability_spec is not None
    assert policy.capability_spec.required == frozenset({"wizard"})


def test_r225_unrecognized_source_capabilities_not_legacy_ok(tmp_path: Path) -> None:
    """Dynamic capability getter without manifest must not import as legacy."""
    info = tmp_path / "p.cdmp"
    info.write_text(
        textwrap.dedent(
            """\
            [Core]
            Name = Dyn
            Module = .

            [Documentation]
            Author = t
            Version = 1.0.0
            Description = missing Codimension
            """
        ),
        encoding="utf-8",
    )
    (tmp_path / "__init__.py").write_text(
        textwrap.dedent(
            """\
            from plugins.categories.wizardiface import WizardInterface

            class Demo(WizardInterface):
                @staticmethod
                def getCapabilityRequirements():
                    return __import__("plugins.capabilities", fromlist=["PluginCapabilitySpec"]).PluginCapabilitySpec(
                        required=frozenset({"wizard"})
                    )
            """
        ),
        encoding="utf-8",
    )
    policy = build_static_plugin_policy(
        info_path=str(info),
        module_filepath=str(tmp_path / "__init__"),
        require_manifest=True,
    )
    decision = evaluate_static_plugin_policy(policy, ide_version="5.0.0")
    assert not decision.ok
