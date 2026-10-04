#!/usr/bin/python3
"""Wired and Wi-Fi status with live transfer rates.

Shows every connected physical interface: Ethernet as a cable icon, Wi-Fi as
signal bars with the network name. The detailed view adds the IP address.
"""
import os
import time

from common import Module, fg, icon, run

NET = "/sys/class/net"

m = Module("network", interval=2)
last = {}           # interface -> (time, rx bytes, tx bytes)
wifi_cache = {}     # interface -> (time, ssid, signal)


def read(path, default=""):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def interfaces():
    """Physical interfaces that are up, Ethernet first."""
    out = []
    for name in sorted(os.listdir(NET)):
        base = os.path.join(NET, name)
        if not os.path.exists(os.path.join(base, "device")):
            continue                                    # lo, docker0, bridges, VPNs
        if read(os.path.join(base, "operstate")) != "up":
            continue
        out.append((os.path.isdir(os.path.join(base, "wireless")), name))
    return sorted(out)


def rate(n):
    for unit in ("B", "K", "M", "G"):
        if n < 1000 or unit == "G":
            return f"{n:4.0f}{unit}" if unit == "B" else f"{n:4.1f}{unit}"
        n /= 1024


def speeds(name):
    now = time.monotonic()
    rx = int(read(f"{NET}/{name}/statistics/rx_bytes", "0"))
    tx = int(read(f"{NET}/{name}/statistics/tx_bytes", "0"))
    t0, rx0, tx0 = last.get(name, (now, rx, tx))
    last[name] = (now, rx, tx)
    dt = max(now - t0, 1e-3)
    return (rx - rx0) / dt if now > t0 else 0, (tx - tx0) / dt if now > t0 else 0


def wifi(name):
    cached = wifi_cache.get(name)
    if cached and time.monotonic() - cached[0] < 15:
        return cached[1:]
    ssid, signal = "Wi-Fi", 0
    for line in run("nmcli", "-t", "-f", "IN-USE,SSID,SIGNAL", "device", "wifi", "list",
                    "ifname", name, "--rescan", "no").splitlines():
        if line.startswith("*:"):
            parts = line.split(":")
            ssid, signal = parts[1] or "Wi-Fi", int(parts[-1] or 0)
    wifi_cache[name] = (time.monotonic(), ssid, signal)
    return ssid, signal


def address(name):
    for line in run("ip", "-4", "-o", "addr", "show", "dev", name).splitlines():
        parts = line.split()
        if "inet" in parts:
            return parts[parts.index("inet") + 1].split("/")[0]
    return ""


def render():
    parts = []
    for wireless, name in interfaces():
        down, up = speeds(name)
        if wireless:
            ssid, signal = wifi(name)
            bars = "󰤟󰤢󰤥󰤨"[min(3, signal // 25)]
            text = f"{icon(bars, 'sky')} {ssid}"
        else:
            text = icon("󰈀", "mint")
        text += f" {fg('󱦳', 'label')}{rate(down)} {fg('󱦲', 'label')}{rate(up)}"
        if m.expanded:
            text += " " + fg(address(name) or name, "label")
        parts.append(text)
    if not parts:
        return f"{icon('󰤮', 'dim')} {fg('offline', 'dim')}"
    return "  ".join(parts)


m.loop(render)
