#!/usr/bin/env bash
# Launch Codimension from this repo's .venv.
# Usage:
#   ./scripts/run_codimension.sh
#   ./scripts/run_codimension.sh path/to/project.cdm3
#   ./scripts/run_codimension.sh --safe-mode
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
CDM="${ROOT}/.venv/bin/codimension"

case "$ROOT" in
  */.local/share/Trash/*|*/Trash/*|*/.Trash/*)
    echo "error: refusing to launch from Trash checkout: $ROOT" >&2
    echo "hint: cd -P \$HOME/codimension && ./scripts/run_codimension.sh" >&2
    exit 1
    ;;
esac

if [[ ! -x "$CDM" ]]; then
  echo "error: missing $CDM" >&2
  echo "hint: ./scripts/codimension_ctl.sh install --yes" >&2
  exit 1
fi

# Repo root on PYTHONPATH so ``cdmplugins`` resolves; the ``codimension`` package
# itself must come from the editable install (do NOT put ROOT/codimension first —
# that shadows the package with the top-level ``codimension.py`` module).
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

exec "$CDM" "$@"
