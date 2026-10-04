"""Shared helpers for the kBar scripts (standard library only)."""
import ctypes
import json
import os
import signal
import subprocess
import threading
import time
import tomllib

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.dirname(SCRIPTS)
TOML_PATH = os.path.join(CONFIG_DIR, "kbar.toml")
RUNTIME_DIR = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
CACHE_DIR = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "kbar")

# "Midnight Ink": the palette shared with pySysMon, pyQuotes and pyReader
THEME = {
    "bg": "#191926", "card": "#20202f", "edge": "#2b2b40", "track": "#2c2c42",
    "fg": "#e8e8f2", "label": "#9a9ab8", "dim": "#62627e",
    "sky": "#7dd3fc", "lavender": "#c4b5fd", "rose": "#f9a8d4",
    "mint": "#86efac", "butter": "#fde68a", "coral": "#fca5a5",
}


def color(name):
    """A theme colour name or a literal "#rrggbb"."""
    name = str(name)
    return name if name.startswith("#") else THEME.get(name, THEME["fg"])


# -- polybar formatting tags ---------------------------------------------------
def fg(text, c):
    return f"%{{F{color(c)}}}{text}%{{F-}}"


def icon(glyph, c):
    """A glyph in the larger icon font (font-1, %{T2}), plus a little room:
    Nerd Font icons are often wider than their advance."""
    return f"%{{T2}}{fg(glyph, c)}%{{T-}}%{{O4}}"


def bold(text):
    return f"%{{T3}}{text}%{{T-}}"


def pill(text, c):
    """Text on the track colour with a coloured underline: the "active" look."""
    return f"%{{B{THEME['track']}}}%{{u{color(c)}}}%{{+u}} {text} %{{-u}}%{{B-}}"


def script(name, *args):
    return " ".join([os.path.join(SCRIPTS, name), *args])


def clickable(text, left=None, middle=None, right=None, up=None, down=None):
    """Wrap text in polybar action tags; ':' must be escaped inside commands."""
    for button, cmd in ((1, left), (2, middle), (3, right), (4, up), (5, down)):
        if cmd:
            text = f"%{{A{button}:{cmd.replace(':', chr(92) + ':')}:}}{text}%{{A}}"
    return text


# -- config & processes ----------------------------------------------------------
def load_config():
    """kbar.toml as a dict ({} if it is missing or invalid)."""
    try:
        with open(TOML_PATH, "rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def run(*cmd, timeout=4):
    """stdout of a command, or "" if it fails."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def busctl_get(bus, service, path, iface, prop):
    out = run("busctl", f"--{bus}", "--json=short", "get-property", service, path, iface, prop)
    try:
        return json.loads(out)["data"] if out else None
    except (ValueError, KeyError):
        return None


def notify(title, body="", icon_name="", urgency="normal"):
    run("notify-send", "--app-name=kBar", f"--urgency={urgency}", *(["-i", icon_name] if icon_name else []),
        title, body)


def _die_with_parent():
    ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, signal.SIGTERM)  # PR_SET_PDEATHSIG


class Module:
    """A polybar tail script: prints a line whenever its output changes.

    `poke <name>` sends SIGUSR1, which toggles the detailed view;
    `poke <name> refresh` sends SIGUSR2, which only redraws.
    """

    def __init__(self, name, interval):
        self.name, self.interval = name, interval
        self.expanded = False
        self.cfg = load_config()
        signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGUSR1, signal.SIGUSR2})
        with open(os.path.join(RUNTIME_DIR, f"kbar-{name}.pid"), "w") as f:
            f.write(str(os.getpid()))

    def watch(self, *cmd, only=None):
        """Redraw on every line a long-running command prints (e.g. gdbus monitor),
        or only on lines containing one of the strings in `only`."""
        def loop():
            while True:
                try:
                    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                         text=True, preexec_fn=_die_with_parent)
                    for line in p.stdout:
                        if only is None or any(s in line for s in only):
                            os.kill(os.getpid(), signal.SIGUSR2)
                    p.wait()
                except OSError:
                    pass
                time.sleep(5)
        threading.Thread(target=loop, daemon=True).start()

    def watch_files(self, paths):
        """Redraw whenever one of these files is opened or closed (inotify)."""
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        fd = libc.inotify_init1(0o2000000)                    # IN_CLOEXEC
        if fd < 0:
            return
        for path in paths:
            libc.inotify_add_watch(fd, os.fsencode(path), 0x20 | 0x08 | 0x10)  # open, close (write / nowrite)

        def loop():
            while os.read(fd, 4096):
                os.kill(os.getpid(), signal.SIGUSR2)
        threading.Thread(target=loop, daemon=True).start()

    def wait(self, timeout):
        """Sleep until timeout or a poke; returns the signal number (or None)."""
        sig = signal.sigtimedwait({signal.SIGUSR1, signal.SIGUSR2}, max(0.05, timeout))
        if not sig:
            return None
        if sig.si_signo == signal.SIGUSR1:
            self.expanded = not self.expanded
        self.cfg = load_config()
        return sig.si_signo

    def loop(self, render):
        last = None
        while True:
            try:
                line = render()
            except Exception as e:  # never let one bad read kill the module
                line = fg(f"{self.name}: {e}", "coral")
            if line != last:
                print(line, flush=True)
                last = line
            self.wait(self.interval)
