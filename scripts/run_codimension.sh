#!/usr/bin/env bash
# Launch Codimension from this repo's .venv (thin wrapper).
# Prefer: ./scripts/codimension_ctl.sh run
# Usage:
#   ./scripts/run_codimension.sh
#   ./scripts/run_codimension.sh path/to/project.cdm3
#   ./scripts/run_codimension.sh --safe-mode
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec "${ROOT}/scripts/codimension_ctl.sh" run "$@"
