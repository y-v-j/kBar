#!/usr/bin/python3
"""KDE virtual desktops, read from KWin over D-Bus.

KWin on Wayland reports a single desktop to X11 clients, so polybar's own
xworkspaces module can't see them. This asks KWin directly and redraws as soon
as KWin signals a change. Click a number to switch to that desktop.
"""
from common import Module, busctl_get, clickable, fg, pill

KWIN = ("org.kde.KWin", "/VirtualDesktopManager", "org.kde.KWin.VirtualDesktopManager")

m = Module("desktops", interval=30)
m.watch("/usr/bin/gdbus", "monitor", "--session", "--dest", KWIN[0], "--object-path", KWIN[1])


def render():
    desktops = busctl_get("user", *KWIN, "desktops") or []
    current = busctl_get("user", *KWIN, "current")
    labels = m.cfg.get("desktops", {}).get("labels", [])
    cells = []
    for index, ident, name in sorted(desktops):
        label = labels[index] if index < len(labels) else str(index + 1)
        cell = pill(fg(label, "lavender"), "lavender") if ident == current else fg(f" {label} ", "dim")
        cells.append(clickable(cell, left=f"busctl --user set-property {' '.join(KWIN)} current s {ident}"))
    return " ".join(cells) or fg("󰍹", "dim")


m.loop(render)
