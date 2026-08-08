# -*- coding: utf-8 -*-
#
# codimension - plugin API / capability negotiation (R150)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Host ↔ plugin API version and capability negotiation (R150).

Pure helpers (no Qt). The host advertises :data:`HOST_PLUGIN_API_VERSION`
and :data:`HOST_CAPABILITIES`. A plugin may declare requirements via
:class:`PluginCapabilitySpec` (from ``getCapabilityRequirements()``).
Missing declaration means “compatible with any host” (backward compatible).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Bump when breaking the plugin host surface (activate hooks, IDEAccess, …).
HOST_PLUGIN_API_VERSION = 1

# Capabilities the current host implements for plugins.
HOST_CAPABILITIES: frozenset[str] = frozenset(
    {
        "wizard",
        "vcs",
        "side_panels",
        "side_bars",
        "status_bar",
        "editors_manager",
        "project",
    }
)


@dataclass(frozen=True)
class PluginCapabilitySpec:
    """What a plugin requires from the host.

    * ``min_api_version`` — host must be at least this major.
    * ``max_api_version`` — if set, host must be at most this major
      (rejects plugins that cannot run on a newer host).
    * ``required`` — capability names the host must advertise.
    """

    min_api_version: int = 1
    max_api_version: Optional[int] = None
    required: frozenset[str] = field(default_factory=frozenset)
    optional: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class CapabilityNegotiationResult:
    """Outcome of negotiating a plugin against the host."""

    ok: bool
    reason: str = ""
    missing: frozenset[str] = field(default_factory=frozenset)


def negotiate_plugin_capabilities(
    spec: Optional[PluginCapabilitySpec],
    *,
    host_api_version: int = HOST_PLUGIN_API_VERSION,
    host_capabilities: frozenset[str] = HOST_CAPABILITIES,
) -> CapabilityNegotiationResult:
    """Return whether ``spec`` is compatible with the host.

    ``None`` spec → accepted (legacy plugins without capability metadata).
    """
    if spec is None:
        return CapabilityNegotiationResult(ok=True, reason="no capability requirements")

    min_api = int(spec.min_api_version)
    if host_api_version < min_api:
        return CapabilityNegotiationResult(
            ok=False,
            reason=(f"host plugin API {host_api_version} is older than plugin minimum {min_api}"),
        )

    if spec.max_api_version is not None and host_api_version > int(spec.max_api_version):
        return CapabilityNegotiationResult(
            ok=False,
            reason=(f"host plugin API {host_api_version} is newer than plugin maximum {spec.max_api_version}"),
        )

    missing = frozenset(spec.required) - frozenset(host_capabilities)
    if missing:
        ordered = ", ".join(sorted(missing))
        return CapabilityNegotiationResult(
            ok=False,
            reason=f"host missing required capabilities: {ordered}",
            missing=missing,
        )

    return CapabilityNegotiationResult(ok=True, reason="compatible")


__all__ = [
    "HOST_CAPABILITIES",
    "HOST_PLUGIN_API_VERSION",
    "CapabilityNegotiationResult",
    "PluginCapabilitySpec",
    "negotiate_plugin_capabilities",
]
