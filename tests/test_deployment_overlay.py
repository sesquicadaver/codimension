# -*- coding: utf-8 -*-
"""R162: deployment overlay Dockerfile / Compose detection."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import parsers  # noqa: E402,F401
import pytest

_CODIM = Path(__file__).resolve().parents[1] / "codimension"
_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "deployment"


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


def test_classify_dockerfile_and_compose_names() -> None:
    from utils.deployment_overlay import classify_deployment_path, is_compose_name, is_dockerfile_name

    assert is_dockerfile_name("Dockerfile")
    assert is_dockerfile_name("Dockerfile.prod")
    assert is_dockerfile_name("app.dockerfile")
    assert not is_dockerfile_name("docker-compose.yml")
    assert is_compose_name("compose.yml")
    assert is_compose_name("docker-compose.yaml")
    assert is_compose_name("docker-compose.override.yml")
    assert classify_deployment_path("/x/Dockerfile") == "dockerfile"
    assert classify_deployment_path("/x/compose.yml") == "compose"
    assert classify_deployment_path("/x/readme.md") is None


def test_detect_deployment_artifacts_on_fixture() -> None:
    from utils.deployment_overlay import detect_deployment_artifacts, format_deployment_badge, relative_hint_paths

    assert _FIXTURE.is_dir()
    hints = detect_deployment_artifacts(str(_FIXTURE))
    assert hints.has_docker
    assert hints.has_compose
    assert any(p.endswith("Dockerfile") for p in hints.dockerfiles)
    assert any(p.endswith("Dockerfile.dev") for p in hints.dockerfiles)
    assert any(p.endswith("compose.yml") for p in hints.compose_files)
    assert any(p.endswith("docker-compose.yaml") for p in hints.compose_files)

    badge = format_deployment_badge(hints)
    assert badge.docker_badge.startswith("deploy:docker")
    assert badge.compose_badge.startswith("compose:")
    assert "Dockerfiles:" in badge.tooltip
    rel = relative_hint_paths(hints)
    assert "Dockerfile" in rel
    assert "compose.yml" in rel


def test_detect_from_explicit_paths_only(tmp_path: Path) -> None:
    from utils.deployment_overlay import detect_deployment_artifacts

    docker = tmp_path / "Dockerfile"
    noise = tmp_path / "readme.md"
    docker.write_text("FROM scratch\n", encoding="utf-8")
    noise.write_text("x\n", encoding="utf-8")
    other = tmp_path / "other" / "compose.yml"
    other.parent.mkdir()
    other.write_text("services: {}\n", encoding="utf-8")

    hints = detect_deployment_artifacts(str(tmp_path), paths=[str(docker), str(noise)])
    assert hints.dockerfiles == (str(docker.resolve()),)
    assert hints.compose_files == ()


def test_deployment_layer_register_and_notify(tmp_path: Path) -> None:
    from utils.deployment_overlay import DEPLOYMENT_LAYER_ID, DeploymentOverlayLayer
    from utils.overlay_host import flow_overlay_host, notify_flow_overlays

    (tmp_path / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    host = flow_overlay_host()
    host.registry = type(host.registry)()
    layer = DeploymentOverlayLayer()
    host.register(layer)
    assert host.registry.has(DEPLOYMENT_LAYER_ID)
    seen: list = []
    layer.add_sink(seen.append)
    notify_flow_overlays("deploy")
    assert layer.last_badge is not None
    assert len(seen) == 1


def test_ensure_deployment_overlay_idempotent() -> None:
    from utils.deployment_overlay import DEPLOYMENT_LAYER_ID, ensure_deployment_overlay
    from utils.overlay_host import flow_overlay_host

    host = flow_overlay_host()
    host.registry = type(host.registry)()
    assert ensure_deployment_overlay(host) is ensure_deployment_overlay(host)
    assert host.registry.has(DEPLOYMENT_LAYER_ID)


def test_flowuiwidget_registers_deployment_overlay_static() -> None:
    path = Path(__file__).resolve().parents[1] / "codimension" / "editor" / "flowuiwidget.py"
    text = path.read_text(encoding="utf-8")
    assert "ensure_deployment_overlay" in text
    assert "__onDeployOverlayBadge" in text


def test_flowuinavbar_has_deploy_badge_api_static() -> None:
    path = Path(__file__).resolve().parents[1] / "codimension" / "editor" / "flowuinavbar.py"
    text = path.read_text(encoding="utf-8")
    assert "setDeployBadges" in text
    assert "__deployDockerBadge" in text
