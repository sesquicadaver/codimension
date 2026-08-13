#!/usr/bin/env bash
# Codimension local deploy / remove (repo checkout + .venv).
#
# Usage:
#   ./scripts/codimension_ctl.sh install [--minimal|--tools] [--desktop] [--reinstall] [--yes]
#   ./scripts/codimension_ctl.sh uninstall [--purge-config] [--keep-venv] [--yes]
#   ./scripts/codimension_ctl.sh -h|--help
#
# Launch after install: ./scripts/run_codimension.sh
# Non-interactive: pass --yes where confirmation would be required.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if command -v realpath >/dev/null 2>&1; then
  ROOT="$(realpath "$ROOT")"
fi
VENV="${ROOT}/.venv"
PY="${VENV}/bin/python"
PIP="${VENV}/bin/pip"
CDM="${VENV}/bin/codimension"
RUN_SH="${ROOT}/scripts/run_codimension.sh"
DESKTOP_DIR="${XDG_DATA_HOME:-${HOME}/.local/share}/applications"
DESKTOP_FILE="${DESKTOP_DIR}/codimension-local.desktop"
ICON_SRC="${ROOT}/resources/codimension.png"
ICON_DST="${XDG_DATA_HOME:-${HOME}/.local/share}/icons/hicolor/256x256/apps/codimension.png"
CONFIG_DIR="${HOME}/.codimension3"

YES=0
MINIMAL=0
TOOLS=1
DESKTOP=0
REINSTALL=0
PURGE_CONFIG=0
KEEP_VENV=0

die() {
  echo "error: $*" >&2
  exit 1
}

info() {
  echo "==> $*"
}

usage() {
  cat <<'EOF'
Codimension local deploy / remove (repo checkout + .venv).

Usage:
  ./scripts/codimension_ctl.sh install [--minimal|--tools] [--desktop] [--reinstall] [--yes]
  ./scripts/codimension_ctl.sh uninstall [--purge-config] [--keep-venv] [--yes]
  ./scripts/codimension_ctl.sh -h|--help

Launch: ./scripts/run_codimension.sh
Non-interactive: pass --yes where confirmation would be required.
EOF
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

refuse_trash_checkout() {
  # Desktop Environments often refuse to launch Exec= from Trash; also a common
  # footgun after moving an old clone to the bin and re-running ctl from there.
  case "$ROOT" in
    */.local/share/Trash/*|*/Trash/*|*/.Trash/*)
      die "refusing install from Trash checkout: $ROOT
Run ctl from a real clone, e.g.:
  ~/codimension/scripts/codimension_ctl.sh install --desktop --yes
  # or:  /path/to/git-clone/scripts/codimension_ctl.sh install --desktop --yes"
      ;;
  esac
}

python_ok() {
  local candidate="$1"
  "$candidate" - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
}

pick_python() {
  local c
  for c in "${PYTHON:-}" python3.13 python3.12 python3.11 python3.10 python3; do
    [[ -z "$c" ]] && continue
    if command -v "$c" >/dev/null 2>&1 && python_ok "$(command -v "$c")"; then
      command -v "$c"
      return 0
    fi
  done
  die "need Python >= 3.10 (set PYTHON=/path/to/python if needed)"
}

confirm() {
  local msg="$1"
  if [[ "$YES" -eq 1 ]]; then
    return 0
  fi
  if [[ ! -t 0 ]]; then
    die "refusing '$msg' without --yes (stdin is not a TTY)"
  fi
  read -r -p "$msg [y/N] " ans
  [[ "$ans" == "y" || "$ans" == "Y" || "$ans" == "yes" ]]
}

install_desktop() {
  [[ -x "$RUN_SH" ]] || die "launcher missing: $RUN_SH"
  mkdir -p "$DESKTOP_DIR" "$(dirname "$ICON_DST")"
  if [[ -f "$ICON_SRC" ]]; then
    cp -f "$ICON_SRC" "$ICON_DST"
  fi
  # Use run_codimension.sh (sets PYTHONPATH) — not a raw venv entry point.
  # Quote paths for spaces; %F stays outside quotes per Desktop Entry Spec.
  cat >"$DESKTOP_FILE" <<EOF
[Desktop Entry]
Name=Codimension
GenericName=Codimension
Comment=Codimension Python IDE (checkout: ${ROOT})
Exec=${RUN_SH} %F
TryExec=${RUN_SH}
Path=${ROOT}
Terminal=false
Type=Application
Icon=codimension
Categories=Development;IDE;
MimeType=application/x-codimension-project;
StartupNotify=true
EOF
  if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
  fi
  info "desktop entry: $DESKTOP_FILE"
  info "menu Exec -> $RUN_SH"
}

remove_desktop() {
  if [[ -f "$DESKTOP_FILE" ]]; then
    rm -f "$DESKTOP_FILE"
    info "removed $DESKTOP_FILE"
  fi
  if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
  fi
}

cmd_install() {
  refuse_trash_checkout
  need_cmd python3
  local base_py
  base_py="$(pick_python)"
  info "base Python: $base_py ($("$base_py" -V 2>&1))"
  info "install ROOT: $ROOT"

  if [[ "$REINSTALL" -eq 1 && -d "$VENV" ]]; then
    confirm "Remove existing venv at $VENV?" || die "aborted"
    info "removing $VENV"
    rm -rf "$VENV"
  fi

  if [[ ! -d "$VENV" ]]; then
    info "creating venv"
    "$base_py" -m venv "$VENV"
  fi
  [[ -x "$PY" ]] || die "venv python missing: $PY"
  # Detect relocated/copied venvs whose shebangs still point elsewhere.
  local venv_prefix
  venv_prefix="$("$PY" -c 'import sys; print(sys.prefix)')"
  if [[ "$venv_prefix" != "$VENV" ]]; then
    die "venv is broken/relocated: python prefix is $venv_prefix (expected $VENV). Re-run with --reinstall"
  fi

  info "upgrading pip"
  "$PY" -m pip install --upgrade pip wheel setuptools

  local spec="."
  if [[ "$MINIMAL" -eq 1 ]]; then
    TOOLS=0
  fi
  if [[ "$TOOLS" -eq 1 ]]; then
    spec=".[tools,lint,test,security,ssh]"
  fi

  # Always install from repo root — ``pip install -e .`` follows the caller's CWD,
  # so running ``./codimension_ctl.sh`` from ``scripts/`` would otherwise target scripts/.
  [[ -f "${ROOT}/pyproject.toml" ]] || die "pyproject.toml missing under ROOT=$ROOT"
  info "installing editable $spec (from $ROOT)"
  (
    cd "$ROOT"
    # Prefer ``python -m pip`` — a relocated venv can leave ``bin/pip`` pointing elsewhere.
    "$PY" -m pip install -e "$spec"
  )

  # pylint/astroid pin wrapt<1.13; on 3.11+ that wrapt is broken — refresh without deps.
  local major minor
  major="$("$PY" -c 'import sys; print(sys.version_info.major)')"
  minor="$("$PY" -c 'import sys; print(sys.version_info.minor)')"
  if [[ "$major" -gt 3 || ( "$major" -eq 3 && "$minor" -ge 11 ) ]]; then
    info "Python ${major}.${minor}: installing wrapt>=1.14 --no-deps (pylint stack)"
    "$PY" -m pip install 'wrapt>=1.14' --no-deps || true
  fi

  [[ -x "$CDM" ]] || die "entry point missing after install: $CDM"

  info "smoke import"
  "$PY" -c 'import codimension, cdmplugins; print("ok", codimension.__file__)'

  if [[ "$DESKTOP" -eq 1 ]]; then
    install_desktop
  fi

  info "deploy complete"
  echo
  echo "Run:  ./scripts/run_codimension.sh"
  echo "      # or: $CDM"
  if [[ "$DESKTOP" -eq 1 ]]; then
    echo "Menu: Codimension  ($DESKTOP_FILE)"
  else
    echo "Menu: add with  ./scripts/codimension_ctl.sh install --desktop --yes"
  fi
  echo
  echo "Remove:"
  echo "  ./scripts/codimension_ctl.sh uninstall --yes"
  echo "  ./scripts/codimension_ctl.sh uninstall --purge-config --yes"
}

cmd_uninstall() {
  if [[ -d "$VENV" && "$KEEP_VENV" -eq 0 ]]; then
    confirm "Delete venv $VENV?" || die "aborted"
    info "removing $VENV"
    rm -rf "$VENV"
  elif [[ -x "$PIP" && "$KEEP_VENV" -eq 1 ]]; then
    info "pip uninstall codimension (venv kept)"
    "$PIP" uninstall -y codimension || true
  fi

  remove_desktop

  if [[ "$PURGE_CONFIG" -eq 1 ]]; then
    if [[ -d "$CONFIG_DIR" ]]; then
      confirm "Delete IDE config $CONFIG_DIR (recent projects, settings)?" || die "aborted"
      info "removing $CONFIG_DIR"
      rm -rf "$CONFIG_DIR"
    else
      info "config dir absent: $CONFIG_DIR"
    fi
  else
    info "kept config: $CONFIG_DIR (use --purge-config to remove)"
  fi

  info "uninstall complete"
}

# ---- argv ----
[[ $# -ge 1 ]] || { usage; exit 2; }
CMD="$1"
shift

case "$CMD" in
  -h|--help|help)
    usage
    exit 0
    ;;
  install|uninstall) ;;
  *)
    die "unknown command: $CMD (try --help)"
    ;;
esac

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes|-y) YES=1 ;;
    --minimal) MINIMAL=1; TOOLS=0 ;;
    --tools) TOOLS=1; MINIMAL=0 ;;
    --desktop) DESKTOP=1 ;;
    --reinstall) REINSTALL=1 ;;
    --purge-config) PURGE_CONFIG=1 ;;
    --keep-venv) KEEP_VENV=1 ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown option for $CMD: $1"
      ;;
  esac
  shift
done

case "$CMD" in
  install) cmd_install ;;
  uninstall) cmd_uninstall ;;
esac
