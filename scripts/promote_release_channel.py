#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI: promote release channel / validate tags (R181).

Examples::

    # Dry-run next step from current cdmverspec.release_channel
    python scripts/promote_release_channel.py --to beta

    # Write release_channel into cdmverspec.py
    python scripts/promote_release_channel.py --to stable --apply

    # CI: validate a pushed tag against cdmverspec
    python scripts/promote_release_channel.py --validate-tag v4.12.0
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CODIM = _REPO_ROOT / "codimension"
if str(_CODIM) not in sys.path:
    sys.path.insert(0, str(_CODIM))

import cdmverspec  # noqa: E402
from utils.channel_promotion import (  # noqa: E402
    PROMOTION_ORDER,
    apply_promotion_to_cdmverspec,
    default_cdmverspec_path,
    format_plan,
    next_channel,
    plan_promotion,
    validate_tag_against_cdmverspec,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Promote Codimension release channel (dev→beta→stable) or validate a tag.",
    )
    parser.add_argument(
        "--to",
        choices=list(PROMOTION_ORDER),
        help="Target channel (forward-only on the ladder).",
    )
    parser.add_argument(
        "--from-channel",
        dest="from_channel",
        choices=list(PROMOTION_ORDER),
        help="Override source channel (default: cdmverspec.release_channel).",
    )
    parser.add_argument(
        "--version",
        help="Override version used for tag suggestion (default: cdmverspec.version).",
    )
    parser.add_argument(
        "--allow-skip",
        action="store_true",
        help="Allow jumping more than one step (e.g. dev→stable).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write release_channel into cdmverspec.py (otherwise dry-run).",
    )
    parser.add_argument(
        "--cdmverspec",
        type=Path,
        default=None,
        help="Path to cdmverspec.py (default: package file).",
    )
    parser.add_argument(
        "--validate-tag",
        metavar="TAG",
        help="Validate TAG against cdmverspec version + channel shape (CI).",
    )
    parser.add_argument(
        "--next",
        action="store_true",
        help="Print the next channel after the current one and exit.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    args = _build_parser().parse_args(argv)
    cdm_path = args.cdmverspec or default_cdmverspec_path(_CODIM)

    if args.validate_tag:
        try:
            validate_tag_against_cdmverspec(args.validate_tag)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print(f"OK: tag {args.validate_tag} matches cdmverspec {cdmverspec.version} ({cdmverspec.release_channel})")
        return 0

    if args.next:
        nxt = next_channel(args.from_channel or cdmverspec.release_channel)
        if nxt is None:
            print("stable (already at top of ladder)")
            return 0
        print(nxt)
        return 0

    if not args.to:
        print("ERROR: pass --to CHANNEL, --next, or --validate-tag TAG", file=sys.stderr)
        return 2

    try:
        plan = plan_promotion(
            to_channel=args.to,
            from_channel=args.from_channel,
            version=args.version,
            allow_skip=args.allow_skip,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(format_plan(plan))
    if not args.apply:
        print("\nDry-run only (pass --apply to write cdmverspec.release_channel).")
        return 0

    apply_promotion_to_cdmverspec(cdm_path, plan)
    print(f"\nWrote release_channel={plan.to_channel!r} → {cdm_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
