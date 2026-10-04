#!/usr/bin/python3
"""Battery level and the active power profile. Click for the battery popup
(time left, power draw, health, charge limit, power profiles).
"""
import glob

from common import Module, busctl_get, fg, icon

PPD = ("net.hadess.PowerProfiles", "/net/hadess/PowerProfiles", "net.hadess.PowerProfiles")
LEVELS = "".join(map(chr, range(0xF007A, 0xF0083))) + "\U000f0079"   # battery 10%, 20% … 90%, full
PROFILES = (("power-saver", "󰌪", "Saver", "mint"),
            ("balanced", "󰗑", "Balanced", "sky"),
            ("performance", "󱓞", "Performance", "coral"))

def read(path, default=None):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def find(kind):
    for d in sorted(glob.glob("/sys/class/power_supply/*")):
        if read(f"{d}/type") == kind and read(f"{d}/scope", "System") != "Device":
            return d
    return None


BAT, AC = find("Battery"), find("Mains")


def num(name):
    v = read(f"{BAT}/{name}")
    return int(v) if v and v.lstrip("-").isdigit() else None


def duration(hours):
    h, mins = divmod(round(hours * 60), 60)
    return f"{h}h {mins:02d}m" if h else f"{mins} min"


def details(status):
    """Time left, watts, health and charge limit (charge_* or energy_* sysfs)."""
    now, full, design = (num("charge_now"), num("charge_full"), num("charge_full_design"))
    rate = num("current_now")
    if now is None:
        now, full, design, rate = num("energy_now"), num("energy_full"), num("energy_full_design"), num("power_now")
    out = []
    if rate and now is not None and full:
        if status == "Charging":
            out.append(f"full in {duration((full - now) / rate)}")
        elif status == "Discharging":
            out.append(f"{duration(now / rate)} left")
    if num("power_now"):
        out.append(f"{num('power_now') / 1e6:.1f} W")
    elif rate and num("voltage_now"):
        out.append(f"{rate * num('voltage_now') / 1e12:.1f} W")
    if full and design:
        out.append(f"health {round(100 * full / design)}%")
    limit = num("charge_control_end_threshold")
    if limit and limit < 100:
        out.append(f"limit {limit}%")
    return out


def state():
    """The battery's level, status, glyph and colour, its details and the
    active power profile; None without a battery."""
    if not BAT:
        return None
    pct = num("capacity") or 0
    status = read(f"{BAT}/status", "Unknown")
    plugged = read(f"{AC}/online") == "1" if AC else status == "Charging"
    if status == "Charging":
        glyph = "\U000f0084"                        # battery charging
    elif plugged and status in ("Full", "Not charging"):
        glyph = "\U000f06a5"                        # power plug
    else:
        glyph = "\U000f0083" if pct < 10 else LEVELS[min(9, pct // 10 - 1)]
    return {"pct": pct, "status": status, "plugged": plugged, "glyph": glyph,
            "color": "coral" if pct < 20 else "butter" if pct < 50 else "mint",
            "details": details(status), "profile": busctl_get("system", *PPD, "ActiveProfile")}


def render():
    b = state()
    if not b:
        return ""
    out = f"{icon(b['glyph'], b['color'])} {b['pct']}%"
    for key, g, _, pc in PROFILES:
        if key == b["profile"]:
            out += " " + fg(g, pc)
    return out


if __name__ == "__main__":
    Module("battery", interval=10).loop(render)
