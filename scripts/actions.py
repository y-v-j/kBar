#!/usr/bin/python3
"""Click handlers for kBar.

  actions.py profile <power-saver|balanced|performance>
  actions.py mic-toggle | camera-info
  actions.py wifi-toggle
  actions.py sink-next
"""
import json
import os
import sys

from common import SCRIPTS, notify, run
from privacy import camera_users


def poke(module, how="refresh"):
    run(os.path.join(SCRIPTS, "poke"), module, how)


def profile(name):
    run("busctl", "--system", "set-property", "net.hadess.PowerProfiles", "/net/hadess/PowerProfiles",
        "net.hadess.PowerProfiles", "ActiveProfile", "s", name)
    poke("battery")


def mic_toggle():
    run("pactl", "set-source-mute", "@DEFAULT_SOURCE@", "toggle")
    poke("privacy")


def camera_info():
    users = sorted(camera_users())
    if users:
        notify("Camera in use", "By: " + ", ".join(users), "camera-web", "critical")
    else:
        notify("Camera is off", "No program is using a camera.", "camera-web")


def wifi_toggle():
    on = run("nmcli", "radio", "wifi") == "enabled"
    run("nmcli", "radio", "wifi", "off" if on else "on")
    notify("Wi-Fi " + ("off" if on else "on"), "", "network-wireless")
    poke("network")


def sink_next():
    try:
        sinks = json.loads(run("pactl", "-f", "json", "list", "sinks") or "[]")
    except ValueError:
        return
    if len(sinks) < 2:
        notify("Audio output", "Only one output device is available.", "audio-speakers")
        return
    default = run("pactl", "get-default-sink")
    names = [s["name"] for s in sinks]
    nxt = sinks[(names.index(default) + 1) % len(sinks) if default in names else 0]
    run("pactl", "set-default-sink", nxt["name"])
    notify("Audio output", nxt.get("description", nxt["name"]), "audio-speakers")


COMMANDS = {"mic-toggle": mic_toggle, "camera-info": camera_info, "wifi-toggle": wifi_toggle,
            "sink-next": sink_next}

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "profile":
        profile(sys.argv[2])
    elif len(sys.argv) == 2 and sys.argv[1] in COMMANDS:
        COMMANDS[sys.argv[1]]()
    else:
        sys.exit(__doc__)
