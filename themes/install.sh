#!/usr/bin/env bash
# ==============================================================================
# Midnight Ink for Dolphin and Konsole
#
# Gives two apps the kBar colours; the rest of Plasma keeps its own scheme.
#   ~/.local/share/color-schemes/MidnightInk.colors  Dolphin, and Konsole's window
#   ~/.local/share/icons/MidnightInk/                Breeze Dark with lavender folders (Dolphin)
#   kwinrulesrc: kbar-midnight-ink-dolphin           Dolphin at 96% opacity, like the widgets
#   dolphinrc view fonts                             FantasqueSansM Nerd Font in every Dolphin view
#   ~/.local/share/konsole/MidnightInk.colorscheme   Konsole's terminal colours
#   ~/.local/share/konsole/Midnight Ink.profile      your default profile, recoloured
#   ~/.dir_colors                                    readable ls colours (Fedora-style systems)
#   --terminal-button                                a Terminal on/off button in Dolphin's toolbar
#
# Usage: themes/install.sh [--no-dolphin] [--no-konsole] [--no-ls] [--terminal-button]
#                          [--uninstall]
# ==============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
CONF="${XDG_CONFIG_HOME:-$HOME/.config}"
SCHEMES="${DATA}/color-schemes"
KONSOLE="${DATA}/konsole"
PROFILE="Midnight Ink.profile"
STATE="${CONF}/kbar/themes-previous"     # settings from before the first install, for --uninstall

RULE="kbar-midnight-ink-dolphin"          # KWin window rule id
FONT="FantasqueSansM Nerd Font,11,-1,5,400,0,0,0,0,0,0,0,0,0,0,1"   # the widgets' typeface
UI="${DATA}/kxmlgui5/dolphin/dolphinui.rc"  # Dolphin's toolbar layout, once customised

DOLPHIN=1; KONSOLE_APP=1; LS=1; TERMINAL_BUTTON=0; UNINSTALL=0

BOLD="\033[1m"; CYAN="\033[36m"; GREEN="\033[32m"; YELLOW="\033[33m"; RED="\033[31m"; RESET="\033[0m"
step() { echo -e "${BOLD}${CYAN}==>${RESET} ${BOLD}$*${RESET}"; }
ok()   { echo -e "    ${GREEN}✓${RESET} $*"; }
warn() { echo -e "    ${YELLOW}!${RESET} $*"; }
die()  { echo -e "${RED}✗ $*${RESET}" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-dolphin) DOLPHIN=0 ;;
    --no-konsole) KONSOLE_APP=0 ;;
    --no-ls)      LS=0 ;;
    --terminal-button) TERMINAL_BUTTON=1 ;;
    --uninstall)  UNINSTALL=1 ;;
    -h|--help)    sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "Unknown option: $1 (see --help)" ;;
  esac
  shift
done

KW="$(command -v kwriteconfig6 || command -v kwriteconfig5 || true)"
KR="$(command -v kreadconfig6 || command -v kreadconfig5 || true)"
[[ -n "$KW" && -n "$KR" ]] || die "kwriteconfig6 / kreadconfig6 not found (are you on KDE Plasma?)"

# Remember a setting's value the first time this script changes it
remember() {
  grep -qF "$1|$2|$3|" "$STATE" 2>/dev/null && return
  mkdir -p "$(dirname "$STATE")"
  printf '%s|%s|%s|%s\n' "$1" "$2" "$3" "$("$KR" --file "$1" --group "$2" --key "$3")" >> "$STATE"
}

# KWin window rule: Dolphin at 96% opacity (the widgets' WINDOW_OPACITY)
RULE_KEYS=("Description=Dolphin: Midnight Ink opacity (kBar)" "wmclass=org.kde.dolphin" "wmclassmatch=1"
           "opacityactive=96" "opacityactiverule=2" "opacityinactive=96" "opacityinactiverule=2")
kwin_reload() { busctl --user call org.kde.KWin /KWin org.kde.KWin reconfigure >/dev/null 2>&1 || true; }
kwin_rule_add() {
  local kv rules count
  for kv in "${RULE_KEYS[@]}"; do "$KW" --file kwinrulesrc --group "$RULE" --key "${kv%%=*}" "${kv#*=}"; done
  rules="$("$KR" --file kwinrulesrc --group General --key rules)"
  if [[ ",${rules}," != *",${RULE},"* ]]; then
    count="$("$KR" --file kwinrulesrc --group General --key count)"
    "$KW" --file kwinrulesrc --group General --key rules "${rules:+${rules},}${RULE}"
    "$KW" --file kwinrulesrc --group General --key count "$(( ${count:-0} + 1 ))"
  fi
  kwin_reload
}
kwin_rule_remove() {
  local kv rules count
  rules="$("$KR" --file kwinrulesrc --group General --key rules)"
  [[ ",${rules}," == *",${RULE},"* ]] || return 0
  count="$("$KR" --file kwinrulesrc --group General --key count)"
  rules="$(printf '%s\n' "${rules//,/$'\n'}" | { grep -vxF "$RULE" || true; } | paste -sd, -)"
  "$KW" --file kwinrulesrc --group General --key rules "$rules"
  "$KW" --file kwinrulesrc --group General --key count "$(( ${count:-1} > 0 ? ${count:-1} - 1 : 0 ))"
  for kv in "${RULE_KEYS[@]}"; do "$KW" --file kwinrulesrc --group "$RULE" --key "${kv%%=*}" --delete; done
  kwin_reload
}

# Add or remove the Terminal toggle in Dolphin's main toolbar; prints what it did
toolbar_terminal() {
  [[ -f "$UI" ]] || { echo "no-layout"; return 0; }
  /usr/bin/env python3 - "$UI" "$1" <<'EOF'
import sys
path, mode = sys.argv[1:]
s = open(path, encoding="utf-8").read()
at = s.find('name="mainToolBar"')
if at < 0:
    print("no-layout"); sys.exit()
start = s.rfind("<ToolBar", 0, at)
end = s.index("</ToolBar>", start)
bar, line = s[start:end], '  <Action name="show_terminal_panel"/>\n'
if mode == "add":
    if 'name="show_terminal_panel"' in bar:
        print("present"); sys.exit()
    for anchor in ('  <Action name="split_stash"/>\n', '  <Action name="split_view"/>\n'):
        if anchor in bar:
            bar = bar.replace(anchor, anchor + line, 1)
            break
    else:
        bar = bar.rstrip(" ") + line + " "
    print("added")
else:
    bar = bar.replace(line, "")
    print("removed")
open(path, "w", encoding="utf-8").write(s[:start] + bar + s[end:])
EOF
}

# ------------------------------------------------------------------------------
# Uninstall: put back what was there before
# ------------------------------------------------------------------------------
if [[ $UNINSTALL -eq 1 ]]; then
  step "Removing Midnight Ink from Dolphin and Konsole"
  if [[ -f "$STATE" ]]; then
    while IFS='|' read -r file group key value; do
      if [[ -n "$value" ]]; then
        "$KW" --file "$file" --group "$group" --key "$key" "$value"
      else
        "$KW" --file "$file" --group "$group" --key "$key" --delete
      fi
    done < "$STATE"
    rm -f "$STATE"
    ok "Restored the previous Dolphin and Konsole settings"
  fi
  kwin_rule_remove
  if [[ -f "$STATE.toolbar" ]]; then
    toolbar_terminal remove >/dev/null
    rm -f "$STATE.toolbar"
  fi
  rm -f "${SCHEMES}/MidnightInk.colors" "${KONSOLE}/MidnightInk.colorscheme" "${KONSOLE}/${PROFILE}"
  [[ -d "${DATA}/icons/MidnightInk" ]] && rm -rf -- "${DATA}/icons/MidnightInk"
  if [[ -f "$HOME/.dir_colors" ]] && cmp -s "$HOME/.dir_colors" "${HERE}/dir_colors"; then
    rm -f "$HOME/.dir_colors"
  fi
  ok "Removed the Midnight Ink files. Restart Dolphin and Konsole to see the change."
  exit 0
fi

# ------------------------------------------------------------------------------
# Dolphin (and the window colours of Konsole)
# ------------------------------------------------------------------------------
mkdir -p "$SCHEMES"
install -m 644 "${HERE}/MidnightInk.colors" "${SCHEMES}/"
if [[ $DOLPHIN -eq 1 ]]; then
  step "Dolphin"
  remember dolphinrc UiSettings ColorScheme
  "$KW" --file dolphinrc --group UiSettings --key ColorScheme MidnightInk
  ok "Window colour scheme: Midnight Ink (Dolphin only)"
  # Folder icons follow the Plasma accent, which a per-app scheme can't change:
  # give Dolphin its own icon theme with lavender folders instead.
  if /usr/bin/env python3 "${HERE}/make-icon-theme.py" "${DATA}/icons/MidnightInk" | sed 's/^/    /'; then
    remember dolphinrc Icons Theme
    "$KW" --file dolphinrc --group Icons --key Theme MidnightInk
    ok "Icon theme: Breeze Dark with lavender folders (Dolphin only)"
  else
    warn "Breeze Dark isn't installed, so folders keep the Plasma accent colour"
  fi
  # Pin the file views to the widgets' typeface; menus, toolbar, panels, status
  # bar and title bar follow Plasma's fonts (System Settings > Text & Fonts)
  for mode in IconsMode CompactMode DetailsMode; do
    remember dolphinrc "$mode" UseSystemFont
    remember dolphinrc "$mode" ViewFont
    "$KW" --file dolphinrc --group "$mode" --key UseSystemFont false
    "$KW" --file dolphinrc --group "$mode" --key ViewFont "$FONT"
  done
  ok "View font: FantasqueSansM Nerd Font (icons, compact and details views)"
  kwin_rule_add
  ok "Window opacity: 96%, like the desktop widgets (KWin rule ${RULE})"
fi

if [[ $TERMINAL_BUTTON -eq 1 ]]; then
  step "Dolphin terminal button"
  case "$(toolbar_terminal add)" in
    added)   mkdir -p "$(dirname "$STATE")"; touch "$STATE.toolbar"; ok "Added a Terminal on/off button next to Split" ;;
    present) ok "The toolbar already has the Terminal button" ;;
    *)       warn "Dolphin's toolbar hasn't been customised yet, so there's no layout file to edit."
             warn "Right-click the toolbar > Configure Toolbars… and add \"Terminal\" (or press F4)." ;;
  esac
fi

# ------------------------------------------------------------------------------
# Konsole: terminal colours, a recoloured copy of your default profile, window
# ------------------------------------------------------------------------------
if [[ $KONSOLE_APP -eq 1 ]]; then
  step "Konsole"
  mkdir -p "$KONSOLE"
  install -m 644 "${HERE}/MidnightInk.colorscheme" "${KONSOLE}/"
  remember konsolerc "Desktop Entry" DefaultProfile
  remember konsolerc UiSettings ColorScheme
  # Copy the current default profile so shell, scrollback, keyboard and mouse
  # settings stay as they are; only the appearance keys change.
  /usr/bin/env python3 - "$KONSOLE" "$CONF" "$PROFILE" <<'EOF'
import configparser, os, sys
konsole, conf, name = sys.argv[1:]
def ini(path=None):
    p = configparser.RawConfigParser(strict=False, interpolation=None)
    p.optionxform = str
    if path:
        p.read(path)
    return p
default = ini(os.path.join(conf, "konsolerc")).get("Desktop Entry", "DefaultProfile", fallback="")
target = os.path.join(konsole, name)
source = target if os.path.exists(target) else None              # re-install: keep it
if default and default != name:
    for d in (konsole, "/usr/share/konsole"):
        if os.path.exists(os.path.join(d, default)):
            source = os.path.join(d, default)
            break
p = ini(source)
for section in ("Appearance", "Cursor Options", "General"):
    if not p.has_section(section):
        p.add_section(section)
p["Appearance"].update({"ColorScheme": "MidnightInk", "LineSpacing": "1",
                        "Font": "FantasqueSansM Nerd Font,12,-1,5,400,0,0,0,0,0,0,0,0,0,0,1"})
p["Cursor Options"].update({"UseCustomCursorColor": "true", "CustomCursorColor": "196,181,253",
                            "CustomCursorTextColor": "25,25,38"})
p["General"]["Name"] = "Midnight Ink"
p["General"].setdefault("Parent", "FALLBACK/")
p["General"]["TerminalMargin"] = "12"
with open(target, "w") as f:
    p.write(f, space_around_delimiters=False)
print("    based on " + (os.path.basename(source) if source else "Konsole's built-in defaults"))
EOF
  "$KW" --file konsolerc --group "Desktop Entry" --key DefaultProfile "$PROFILE"
  "$KW" --file konsolerc --group UiSettings --key ColorScheme MidnightInk
  ok "Default profile: Midnight Ink (terminal and window colours)"
fi

# ------------------------------------------------------------------------------
# ls colours
# ------------------------------------------------------------------------------
if [[ $LS -eq 1 ]]; then
  step "ls colours"
  if [[ -e /etc/profile.d/colorls.sh && -e /etc/DIR_COLORS ]]; then
    if [[ ! -e "$HOME/.dir_colors" ]]; then
      install -m 644 "${HERE}/dir_colors" "$HOME/.dir_colors"
      ok "Installed ~/.dir_colors (applies to new shells)"
    elif cmp -s "$HOME/.dir_colors" "${HERE}/dir_colors"; then
      ok "~/.dir_colors is already in place"
    else
      warn "You already have a ~/.dir_colors; left it alone. See ${HERE}/dir_colors for the changes."
    fi
  else
    warn "Add this line to ~/.bashrc (or your shell's rc file) for readable ls highlights:"
    echo "      export LS_COLORS=\"\${LS_COLORS}:ow=30;42:st=30;44:su=30;41:mi=30;41\""
  fi
fi

echo
echo -e "${GREEN}${BOLD}Done.${RESET} Restart Dolphin and Konsole to see Midnight Ink."
echo "  Undo: themes/install.sh --uninstall"
