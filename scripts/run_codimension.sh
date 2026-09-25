#!/usr/bin/env bash
# Launch Codimension from this repo's .venv.
# Usage:
#   ./scripts/run_codimension.sh
#   ./scripts/run_codimension.sh path/to/project.cdm3
#   ./scripts/run_codimension.sh --safe-mode
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
CDM="${ROOT}/.venv/bin/codimension"
PY="${ROOT}/.venv/bin/python"

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

if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
  echo "error: no DISPLAY or WAYLAND_DISPLAY; cannot start the GUI" >&2
  exit 1
fi

# Repo root on PYTHONPATH so ``cdmplugins`` resolves; the ``codimension`` package
# itself must come from the editable install (do NOT put ROOT/codimension first —
# that shadows the package with the top-level ``codimension.py`` module).
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

# PyQt5 ships platform plugins under site-packages. Empty QT_PLUGIN_PATH /
# QT_QPA_PLATFORM_PLUGIN_PATH yields:
#   Could not find the Qt platform plugin "xcb" in ""
if [[ -x "$PY" ]]; then
  QT_PLUGINS="$("$PY" - <<'PY' || true
import os
try:
    from PyQt5.QtCore import QLibraryInfo
    print(QLibraryInfo.location(QLibraryInfo.PluginsPath))
except Exception:
    try:
        import PyQt5
        print(os.path.join(os.path.dirname(PyQt5.__file__), "Qt5", "plugins"))
    except Exception:
        pass
PY
)"
  if [[ -n "${QT_PLUGINS:-}" && -d "${QT_PLUGINS}/platforms" ]]; then
    if [[ -z "${QT_PLUGIN_PATH:-}" ]]; then
      export QT_PLUGIN_PATH="$QT_PLUGINS"
    elif [[ ":${QT_PLUGIN_PATH}:" != *":${QT_PLUGINS}:"* ]]; then
      export QT_PLUGIN_PATH="${QT_PLUGINS}:${QT_PLUGIN_PATH}"
    fi
  fi
fi
# Empty string in the environment is worse than unset for some Qt builds.
if [[ -z "${QT_QPA_PLATFORM_PLUGIN_PATH:-}" ]]; then
  unset QT_QPA_PLATFORM_PLUGIN_PATH || true
fi

exec "$CDM" "$@"
