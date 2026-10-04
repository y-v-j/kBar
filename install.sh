#!/usr/bin/env bash
# ==============================================================================
# kBar - installer
#
# Installs entirely in user space (no root, no rpm-ostree layering):
#   ~/.config/kbar/                          bar config, scripts, kbar.toml
#   ~/.local/share/fonts/FantasqueSansMNerdFont/
#   ~/.config/autostart/kbar.desktop         (default startup method)
# The bar runs as the "kbar" systemd user service.
#
# Usage: ./install.sh [--startup autostart|none] [--python PATH]
#                     [--no-start] [--uninstall] [--help]
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${HOME}/.config/kbar"
FONT_DIR="${HOME}/.local/share/fonts/FantasqueSansMNerdFont"
AUTOSTART_FILE="${HOME}/.config/autostart/kbar.desktop"
CONDA_ENV_NAME="${KBAR_CONDA_ENV:-conky-env}"
FONT_URL="https://github.com/ryanoasis/nerd-fonts/releases/latest/download/FantasqueSansMono.tar.xz"

STARTUP="autostart"
PYTHON=""
START_NOW=1
UNINSTALL=0

BOLD="\033[1m"; CYAN="\033[36m"; GREEN="\033[32m"; YELLOW="\033[33m"; RED="\033[31m"; RESET="\033[0m"
step() { echo -e "${BOLD}${CYAN}==>${RESET} ${BOLD}$*${RESET}"; }
ok()   { echo -e "    ${GREEN}✓${RESET} $*"; }
warn() { echo -e "    ${YELLOW}!${RESET} $*"; }
die()  { echo -e "${RED}✗ $*${RESET}" >&2; exit 1; }

usage() {
  cat <<EOF
kBar installer

Options:
  --startup MODE   How to start at login: autostart (default) or none
  --python PATH    Python for the application menu and popups
                   (needs Tk, ideally built with Xft, and PySide6)
  --no-start       Don't start the bar after installing
  --uninstall      Remove kBar (keeps kbar.toml and the font)
  -h, --help       Show this help

Environment:
  KBAR_CONDA_ENV   Conda env to look in for that Python (default: conky-env)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --startup)   STARTUP="${2:-}"; shift 2 ;;
    --python)    PYTHON="${2:-}"; shift 2 ;;
    --no-start)  START_NOW=0; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    -h|--help)   usage; exit 0 ;;
    *) usage; die "Unknown option: $1" ;;
  esac
done
case "$STARTUP" in autostart|none) ;; *) die "--startup must be autostart or none" ;; esac

stop_running() {
  systemctl --user stop kbar.service 2>/dev/null || true
  systemctl --user reset-failed kbar.service 2>/dev/null || true
}

# ------------------------------------------------------------------------------
# Uninstall
# ------------------------------------------------------------------------------
if [[ $UNINSTALL -eq 1 ]]; then
  step "Uninstalling kBar"
  stop_running
  rm -f "$AUTOSTART_FILE"
  if [[ -d "$APP_DIR" ]]; then
    find "$APP_DIR" -mindepth 1 -maxdepth 1 ! -name kbar.toml -exec rm -rf {} +
  fi
  ok "Removed the bar, its scripts and the startup entry"
  echo "    Kept ${APP_DIR}/kbar.toml and the font (${FONT_DIR})."
  exit 0
fi

for f in config.ini kbar.toml launch.sh scripts/run-bar scripts/common.py scripts/appmenu.py scripts/popup.py; do
  [[ -f "${SCRIPT_DIR}/${f}" ]] || die "Missing ${f} next to install.sh (run it from the project folder)"
done

echo -e "${BOLD}${CYAN}"
echo "  ┌──────────────────────────────────────────────┐"
echo "  │      Installing kBar, a polybar for KDE      │"
echo "  └──────────────────────────────────────────────┘"
echo -e "${RESET}"

# ------------------------------------------------------------------------------
# 1. Requirements
# ------------------------------------------------------------------------------
step "[1/5] Requirements"
command -v polybar >/dev/null || die "polybar is not installed (Fedora/Bazzite: rpm-ostree install polybar; Arch: pacman -S polybar)"
PB_VERSION="$(polybar --version | head -n 1 | awk '{print $2}')"
[[ "$(printf '%s\n3.6\n' "$PB_VERSION" | sort -V | head -n 1)" == "3.6" ]] || die "polybar ${PB_VERSION} is too old (3.6 or newer is needed)"
ok "polybar ${PB_VERSION}"
/usr/bin/python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null \
  || die "/usr/bin/python3 must be Python 3.11 or newer (the module scripts use tomllib)"
ok "$(/usr/bin/python3 --version)"
for tool in busctl gdbus pactl nmcli kstart notify-send polybar-msg systemd-run; do
  command -v "$tool" >/dev/null || warn "${tool} not found: some modules or clicks won't work"
done
[[ "${XDG_CURRENT_DESKTOP:-}" == *KDE* ]] || warn "This doesn't look like a KDE Plasma session; kBar's clicks talk to Plasma"

# ------------------------------------------------------------------------------
# 2. Font
# ------------------------------------------------------------------------------
step "[2/5] Fantasque Sans Mono Nerd Font"
# (no grep -q: an early exit would SIGPIPE fc-list and fail under pipefail)
if fc-list : family 2>/dev/null | grep -i "FantasqueSansM Nerd Font" >/dev/null; then
  ok "Already installed"
else
  command -v curl >/dev/null || die "curl is required to download the font"
  TMP_DIR="$(mktemp -d)"
  trap 'rm -rf "$TMP_DIR"' EXIT
  curl -fsSL -o "${TMP_DIR}/fantasque.tar.xz" "$FONT_URL"
  tar -xJf "${TMP_DIR}/fantasque.tar.xz" -C "$TMP_DIR"
  mkdir -p "$FONT_DIR"
  cp "${TMP_DIR}"/FantasqueSansMNerdFont-*.ttf "${TMP_DIR}/OFL.txt" "$FONT_DIR/"
  fc-cache -f "$FONT_DIR" >/dev/null
  ok "Installed to ${FONT_DIR}"
fi

# ------------------------------------------------------------------------------
# 3. Python for the application menu and popups (Tk + PySide6)
# ------------------------------------------------------------------------------
step "[3/5] Python for the menu and popups"
ui_ok()   { "$1" -c 'import tkinter, PySide6.QtWidgets' >/dev/null 2>&1; }
has_xft() {
  local lib
  lib="$("$1" -c 'import _tkinter; print(_tkinter.__file__)' 2>/dev/null)" || return 1
  ldd "$lib" 2>/dev/null | grep -i xft >/dev/null
}
candidates=()
if [[ -n "$PYTHON" ]]; then
  candidates+=("$PYTHON")
else
  for base in "$HOME/miniforge3" "$HOME/miniconda3" "$HOME/anaconda3"; do
    candidates+=("${base}/envs/${CONDA_ENV_NAME}/bin/python")
  done
  candidates+=("$(command -v python3 || true)")
fi
UI_PY=""
for c in "${candidates[@]}"; do
  [[ -n "$c" && -x "$c" ]] && ui_ok "$c" || continue
  [[ -z "$UI_PY" ]] && UI_PY="$c"
  if has_xft "$c"; then UI_PY="$c"; break; fi   # an Xft Tk draws smooth text: prefer it
done
if [[ -n "$UI_PY" ]]; then
  ok "Using ${UI_PY}"
  has_xft "$UI_PY" || warn "Its Tk has no Xft support: popup text will look blocky"
else
  UI_PY="$(command -v python3)"
  warn "No Python with both tkinter and PySide6 found; the menu and popups won't open."
  warn "Install them (e.g. pip install --user PySide6) or pass --python PATH, then re-run."
fi

# ------------------------------------------------------------------------------
# 4. Install
# ------------------------------------------------------------------------------
step "[4/5] Installing to ${APP_DIR}"
stop_running
mkdir -p "$APP_DIR"
rm -rf "${APP_DIR}/scripts"
cp -r "${SCRIPT_DIR}/scripts" "${APP_DIR}/scripts"
find "${APP_DIR}/scripts" -name __pycache__ -prune -exec rm -rf {} +
cp "${SCRIPT_DIR}/config.ini" "${SCRIPT_DIR}/launch.sh" "$APP_DIR/"
chmod 755 "${APP_DIR}/launch.sh" "${APP_DIR}"/scripts/*
chmod 644 "${APP_DIR}/scripts/common.py"
for f in appmenu.py popup.py; do
  sed -i "1s|.*|#!${UI_PY}|" "${APP_DIR}/scripts/${f}"
done
if [[ -f "${APP_DIR}/kbar.toml" ]]; then
  ok "Kept your kbar.toml"
else
  cp "${SCRIPT_DIR}/kbar.toml" "$APP_DIR/"
  ok "Settings: ${APP_DIR}/kbar.toml"
fi

# ------------------------------------------------------------------------------
# 5. Startup at login
# ------------------------------------------------------------------------------
step "[5/5] Startup at login (${STARTUP})"
if [[ "$STARTUP" == autostart ]]; then
  mkdir -p "$(dirname "$AUTOSTART_FILE")"
  # "~", not "$HOME": systemd's autostart generator escapes "$", so sh would never expand it
  cat > "$AUTOSTART_FILE" <<'EOF'
[Desktop Entry]
Type=Application
Name=kBar
Comment=A polybar for KDE Plasma in the Midnight Ink theme
Exec=sh -c "exec ~/.config/kbar/launch.sh"
X-KDE-autostart-after=panel
X-GNOME-Autostart-enabled=true
EOF
  ok "Autostart entry: ${AUTOSTART_FILE}"
else
  rm -f "$AUTOSTART_FILE"
  ok "No startup entry installed"
fi

if [[ $START_NOW -eq 1 ]]; then
  "${APP_DIR}/launch.sh"
  sleep 2
  systemctl --user is-active --quiet kbar.service && ok "kBar is running" || warn "kBar didn't start: journalctl --user -u kbar"
fi

echo
echo -e "${GREEN}${BOLD}Installation complete!${RESET}"
echo "  Settings:   ${APP_DIR}/kbar.toml (launchers, weather, desktop labels)"
echo "  Restart:    ${APP_DIR}/launch.sh"
echo "  Stop:       systemctl --user stop kbar"
echo "  Uninstall:  ./install.sh --uninstall"
