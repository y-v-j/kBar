#!/usr/bin/env python3
"""Build the "Midnight Ink" icon theme: Breeze Dark with lavender folders.

Breeze tints folder and place icons with the Plasma accent colour, which a
per-app colour scheme can't change. This copies the accent-tinted icons from
the installed Breeze Dark with the lavender baked in, and inherits every other
icon from Breeze Dark. Dolphin uses it through [Icons] Theme in dolphinrc, so
the rest of Plasma keeps its own icons and accent.

  make-icon-theme.py [OUTPUT_DIR]   (default: ~/.local/share/icons/MidnightInk)
"""
import os
import re
import sys

SOURCE = "/usr/share/icons/breeze-dark"
LAVENDER = "#c4b5fd"
CONTEXTS = ("places", "mimetypes")   # folders, home, desktop, network… and inode-directory

data = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(data, "icons", "MidnightInk")
if not os.path.isfile(os.path.join(SOURCE, "index.theme")):
    sys.exit(f"Breeze Dark isn't installed ({SOURCE})")

# The [dir] sections of Breeze Dark's index.theme, to describe the copied folders
sections, current = {}, None
with open(os.path.join(SOURCE, "index.theme"), encoding="utf-8") as f:
    for line in f:
        line = line.rstrip("\n")
        m = re.fullmatch(r"\[(.+)\]", line)
        if m:
            current = m.group(1)
            sections[current] = []
        elif current and line.strip():
            sections[current].append(line)

dirs, count = [], 0
for name in sorted(sections):
    if name.split("/")[0] not in CONTEXTS or not os.path.isdir(os.path.join(SOURCE, name)):
        continue
    written = 0
    for icon in sorted(os.listdir(os.path.join(SOURCE, name))):
        if not icon.endswith(".svg"):
            continue
        try:
            with open(os.path.realpath(os.path.join(SOURCE, name, icon)), encoding="utf-8") as f:
                svg = f.read()
        except (OSError, UnicodeDecodeError):
            continue
        if "ColorScheme-Accent" not in svg or 'id="current-color-scheme"' not in svg:
            continue
        # Rename the stylesheet KDE rewrites with the accent, and give it lavender
        svg = svg.replace('id="current-color-scheme"', 'id="midnight-ink"')
        svg = re.sub(r"(\.ColorScheme-Accent\s*\{\s*color:\s*)#[0-9a-fA-F]{3,8}", rf"\g<1>{LAVENDER}", svg)
        os.makedirs(os.path.join(out, name), exist_ok=True)
        with open(os.path.join(out, name, icon), "w", encoding="utf-8") as f:
            f.write(svg)
        written += 1
    if written:
        dirs.append(name)
        count += written

with open(os.path.join(out, "index.theme"), "w", encoding="utf-8") as f:
    f.write("[Icon Theme]\nName=Midnight Ink\n"
            "Comment=Breeze Dark with lavender folders, for kBar's Midnight Ink theme\n"
            "Inherits=breeze-dark,breeze,hicolor\nHidden=true\n"
            f"Directories={','.join(dirs)}\n")
    for name in dirs:
        f.write(f"\n[{name}]\n" + "\n".join(sections[name]) + "\n")
print(f"{count} icons in {len(dirs)} folders -> {out}")
