#!/usr/bin/python3
"""Camera and microphone indicator.

The camera icon is dim while no program has a video device open and turns
coral (with the program's name) while one does. It redraws when a camera is
opened or closed and when PulseAudio reports a change, not on a timer. The microphone icon shows
mute state; it turns coral while something is recording. Click the
microphone to mute or unmute it, click the camera to see who is using it.
"""
import glob
import json
import os

from common import Module, clickable, fg, icon, run, script

SKIP = {"pipewire", "wireplumber", "pipewire-pulse", "xdg-desktop-portal"}


def camera_users():
    """{program name} for processes holding /dev/video* open (ours only)."""
    devices = set(glob.glob("/dev/video*"))
    users = set()
    uid = os.getuid()
    for pid in filter(str.isdigit, os.listdir("/proc")):
        try:
            if os.stat(f"/proc/{pid}").st_uid != uid:
                continue
            fds = f"/proc/{pid}/fd"
            if any(os.readlink(f"{fds}/{fd}") in devices for fd in os.listdir(fds)):
                with open(f"/proc/{pid}/comm") as f:
                    users.add(f.read().strip())
        except OSError:
            continue
    return users


def mic():
    """(muted, [recording apps]) for the default source."""
    muted = run("pactl", "get-source-mute", "@DEFAULT_SOURCE@").endswith("yes")
    apps = []
    try:
        for out in json.loads(run("pactl", "-f", "json", "list", "source-outputs") or "[]"):
            props = out.get("properties", {})
            if props.get("stream.monitor") == "true" or ".monitor" in str(out.get("source", "")):
                continue
            apps.append(props.get("application.name") or props.get("application.process.binary") or "app")
    except ValueError:
        pass
    return muted, apps


def render():
    users = camera_users()
    real = sorted(users - SKIP) or sorted(users)
    if users:
        cam = icon("󰖠", "coral") + " " + fg(", ".join(real), "coral")
    else:
        cam = icon("󱜷", "dim")
    muted, apps = mic()
    if muted:
        mic_part = icon("󰍭", "dim")
    elif apps:
        mic_part = icon("󰍬", "coral") + " " + fg(", ".join(sorted(set(apps))), "coral")
    else:
        mic_part = icon("󰍬", "label")
    return (clickable(cam, left=script("actions.py", "camera-info"))
            + "  " + clickable(mic_part, left=script("actions.py", "mic-toggle")))


if __name__ == "__main__":
    m = Module("privacy", interval=30)
    m.watch_files(glob.glob("/dev/video*"))    # a camera being opened or closed
    # mute changes, recording streams, a new default source; not "client"
    # events, which our own pactl calls cause
    m.watch("pactl", "subscribe", only=(" on source", " on server"))
    m.loop(render)
