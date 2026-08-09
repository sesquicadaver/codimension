#!/usr/bin/env bash
# Launch Codimension from this repo's .venv (dev checkout).
# Usage:
#   ./scripts/run_codimension.sh
#   ./scripts/run_codimension.sh path/to/project.cdm3
#   ./scripts/run_codimension.sh --safe-mode
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CDM="${ROOT}/.venv/bin/codimension"

if [[ ! -x "$CDM" ]]; then
  echo "error: missing $CDM" >&2
  echo "hint: cd \"$ROOT\" && python3 -m venv .venv && .venv/bin/pip install -e ." >&2
  exit 1
fi

# Prefer the checkout's cdmplugins package over a namespace stub in site-packages.
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

exec "$CDM" "$@"
