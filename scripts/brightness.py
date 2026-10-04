#!/usr/bin/python3
"""Screen brightness through KDE's ScreenBrightness service, plus Night Light.

KDE drives both laptop backlights and external monitors (over DDC/CI), so this
works for the Samsung monitor without root. A moon appears while Night Light
is active.
"""
from common import Module, busctl_get, icon

SB = "org.kde.ScreenBrightness"
NIGHT = ("org.kde.KWin.NightLight", "/org/kde/KWin/NightLight", "org.kde.KWin.NightLight")

m = Module("brightness", interval=60)
m.watch("/usr/bin/gdbus", "monitor", "--session", "--dest", SB)
m.watch("/usr/bin/gdbus", "monitor", "--session", "--dest", NIGHT[0], "--object-path", NIGHT[1])


def render():
    displays = busctl_get("user", SB, "/org/kde/ScreenBrightness", SB, "DisplaysDBusNames") or []
    if not displays:
        return ""
    path = f"/org/kde/ScreenBrightness/{displays[0]}"
    now = busctl_get("user", SB, path, f"{SB}.Display", "Brightness") or 0
    top = busctl_get("user", SB, path, f"{SB}.Display", "MaxBrightness") or 1
    pct = round(100 * now / top)
    glyph = "󰃞" if pct < 34 else "󰃟" if pct < 67 else "󰃠"
    out = f"{icon(glyph, 'butter')}%{{O3}} {pct}%"     # the sun's rays need extra room
    if busctl_get("user", *NIGHT, "running"):
        out += " " + icon("󰖔", "lavender")
    return out


m.loop(render)
