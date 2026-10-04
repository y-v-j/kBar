#!/usr/bin/env python3
"""Themed popups for the bar: a month calendar, the weather forecast and the
battery with its power profiles.

  popup.py calendar | weather | battery   [--at X]

Opens just below the bar, centred on the mouse pointer. Click the module
again, press Esc, right-click the popup or move the pointer in and out to
close it. install.sh points it at a Python whose Tk draws smooth Xft text.
"""
import calendar
import datetime
import json
import os
import signal
import subprocess
import sys
import tkinter as tk
import tkinter.font as tkfont

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import battery  # noqa: E402
from common import CACHE_DIR, RUNTIME_DIR, SCRIPTS, THEME  # noqa: E402
from weather import describe  # noqa: E402

PIDFILE = os.path.join(RUNTIME_DIR, "kbar-popup.pid")
BELOW_BAR = 41 + 8                # bar height + border (config.ini) + a gap
FONT = "FantasqueSansM Nerd Font"


def mix(a, b, t):
    a, b = a.lstrip("#"), b.lstrip("#")
    return "#" + "".join(f"{round(int(a[i:i + 2], 16) * (1 - t) + int(b[i:i + 2], 16) * t):02x}" for i in (0, 2, 4))


def close_open(kind):
    """Close a popup that is already open; True if it was this kind (a toggle)."""
    try:
        with open(PIDFILE) as f:
            pid, open_kind = f.read().split()
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            if b"popup.py" not in f.read():
                return False
        os.kill(int(pid), signal.SIGTERM)
        return open_kind == kind
    except (OSError, ValueError):
        return False


class Popup:
    def __init__(self, kind, width, height):
        self.W, self.H = width, height
        self.at = int(sys.argv[sys.argv.index("--at") + 1]) if "--at" in sys.argv else None
        self.root = r = tk.Tk()
        r.withdraw()
        r.overrideredirect(True)
        r.configure(bg=THEME["bg"])
        try:
            r.attributes("-alpha", 0.97)
        except tk.TclError:
            pass
        family = FONT if FONT in tkfont.families(r) else "monospace"
        font = lambda px, w="normal": tkfont.Font(family=family, size=-px, weight=w)  # noqa: E731
        self.f = {"title": font(17, "bold"), "body": font(14), "small": font(12), "bold": font(14, "bold"),
                  "icon": font(18), "big": font(38, "bold"), "bigicon": font(44)}
        self.cv = tk.Canvas(r, width=width, height=height, bg=THEME["bg"], bd=0,
                            highlightthickness=1, highlightbackground=THEME["edge"])
        self.cv.pack()
        sw = r.winfo_screenwidth()
        centre = self.at if self.at is not None else r.winfo_pointerx()
        x = min(max(24, centre - width // 2), sw - width - 24)
        r.geometry(f"{width}x{height}+{x}+{BELOW_BAR}")

        self.entered = False
        self.leave_job = None
        r.bind("<Escape>", lambda e: self.close())
        self.cv.bind("<Button-3>", lambda e: self.close())
        self.cv.bind("<Enter>", self.on_enter)
        self.cv.bind("<Leave>", self.on_leave)
        r.bind("<FocusOut>", lambda e: self.close() if self.entered else None)
        signal.signal(signal.SIGTERM, lambda *_: self.close())
        self.heartbeat()                       # lets Python run the SIGTERM handler
        with open(PIDFILE, "w") as f:
            f.write(f"{os.getpid()} {kind}")

    def heartbeat(self):
        self.root.after(200, self.heartbeat)

    def on_enter(self, _):
        self.entered = True
        if self.leave_job:
            self.root.after_cancel(self.leave_job)
            self.leave_job = None

    def on_leave(self, _):
        if self.entered:
            self.leave_job = self.root.after(700, self.close)

    def close(self):
        try:
            with open(PIDFILE) as f:
                if f.read().split()[0] == str(os.getpid()):
                    os.remove(PIDFILE)
        except (OSError, IndexError):
            pass
        self.root.destroy()
        sys.exit(0)

    def show(self):
        self.root.deiconify()
        self.root.focus_force()
        self.root.mainloop()

    # drawing helpers, as in pySysMon
    def text(self, x, y, s, font, color, anchor="nw"):
        return self.cv.create_text(x, y, text=s, font=self.f[font], fill=THEME.get(color, color), anchor=anchor)

    def rrect(self, x1, y1, x2, y2, r, **kw):
        r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
               x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return self.cv.create_polygon(pts, smooth=True, splinesteps=10, **kw)

    def button(self, items, action):
        """Make canvas items clickable, with a hand cursor over them."""
        for item in items:
            self.cv.tag_bind(item, "<Button-1>", lambda e: action())
            self.cv.tag_bind(item, "<Enter>", lambda e: self.cv.config(cursor="hand2"))
            self.cv.tag_bind(item, "<Leave>", lambda e: self.cv.config(cursor=""))

    def divider(self, y, pad):
        stops, n = [THEME["sky"], THEME["lavender"], THEME["rose"]], 40
        w = (self.W - 2 * pad) / n
        for i in range(n):
            t = i / (n - 1) * 2
            k = min(int(t), 1)
            self.cv.create_line(pad + i * w, y, pad + (i + 1) * w + 1, y, fill=mix(stops[k], stops[k + 1], t - k), width=2)


class CalendarPopup(Popup):
    def __init__(self):
        super().__init__("calendar", 318, 300)
        today = datetime.date.today()
        self.year, self.month = today.year, today.month
        self.cv.bind("<Button-4>", lambda e: self.shift(-1))
        self.cv.bind("<Button-5>", lambda e: self.shift(1))
        self.draw()

    def shift(self, n):
        m = self.year * 12 + self.month - 1 + n
        self.year, self.month = divmod(m, 12)
        self.month += 1
        self.draw()

    def go_today(self):
        today = datetime.date.today()
        self.year, self.month = today.year, today.month
        self.draw()

    def draw(self):
        cv, T, pad = self.cv, THEME, 18
        cv.delete("all")
        today = datetime.date.today()
        title = self.text(self.W / 2, pad, datetime.date(self.year, self.month, 1).strftime("%B %Y"),
                          "title", "lavender", "n")
        cv.tag_bind(title, "<Button-1>", lambda e: self.go_today())
        for glyph, x, anchor, step in (("󰅁", pad, "nw", -1), ("󰅂", self.W - pad, "ne", 1)):
            b = self.text(x, pad - 1, glyph, "icon", "sky", anchor)
            cv.tag_bind(b, "<Button-1>", lambda e, s=step: self.shift(s))
        self.divider(pad + 34, pad)

        x0, cell, rowh = pad + 26, (self.W - pad - 26 - pad) / 7, 31
        y = pad + 46
        for i, d in enumerate(("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")):
            self.text(x0 + i * cell + cell / 2, y, d, "small", "rose" if i >= 5 else "dim", "n")
        y += 24
        for week in calendar.Calendar(firstweekday=0).monthdatescalendar(self.year, self.month):
            self.text(pad, y + 4, str(week[0].isocalendar()[1]), "small", "dim")
            for i, day in enumerate(week):
                cx = x0 + i * cell + cell / 2
                if day == today:
                    self.rrect(cx - 14, y - 2, cx + 14, y + 24, 9, fill=T["sky"], outline="")
                    self.text(cx, y + 1, str(day.day), "bold", "bg", "n")
                    continue
                c = "dim" if day.month != self.month else ("rose" if i >= 5 else "fg")
                self.text(cx, y + 1, str(day.day), "body", c, "n")
            y += rowh
        foot = self.text(self.W / 2, self.H - pad, today.strftime("%A, %d %B %Y"), "small", "label", "s")
        cv.tag_bind(foot, "<Button-1>", lambda e: self.go_today())


class WeatherPopup(Popup):
    def __init__(self):
        super().__init__("weather", 392, 372)
        try:
            with open(os.path.join(CACHE_DIR, "weather.json")) as f:
                self.cache = json.load(f)
        except (OSError, ValueError):
            self.cache = None
        self.draw()

    def draw(self):
        pad, T = 18, THEME
        if not self.cache:
            self.text(self.W / 2, self.H / 2, "No weather yet: check the connection", "body", "label", "center")
            return
        d = self.cache["data"]
        cur, cu, daily, hourly = d["current"], d["current_units"], d["daily"], d["hourly"]
        deg = cu["temperature_2m"]
        updated = datetime.datetime.fromtimestamp(self.cache["fetched"]).strftime("%H:%M")
        self.text(pad, pad, self.cache["place"], "title", "lavender")
        self.text(self.W - pad, pad + 3, f"updated {updated}", "small", "dim", "ne")
        self.divider(pad + 32, pad)

        glyph, desc, c = describe(cur["weather_code"], cur.get("is_day", 1))
        y = pad + 44
        ic = self.text(pad, y - 4, glyph, "bigicon", c)
        tx = self.cv.bbox(ic)[2] + 12
        t = self.text(tx, y, f"{round(cur['temperature_2m'])}{deg}", "big", "fg")
        rx = self.cv.bbox(t)[2] + 16
        self.text(rx, y + 4, desc, "bold", "fg")
        self.text(rx, y + 26, f"feels {round(cur['apparent_temperature'])}°  ·  󰖎 {cur['relative_humidity_2m']}%",
                  "small", "label")
        sunrise, sunset = daily["sunrise"][0][11:16], daily["sunset"][0][11:16]
        self.text(rx, y + 44, f"󰖝 {round(cur['wind_speed_10m'])} {cu['wind_speed_10m']}  ·  󰖜 {sunrise}  󰖛 {sunset}",
                  "small", "label")

        # next twelve hours, every two hours
        y += 78
        now = cur["time"][:13]
        start = next((i for i, h in enumerate(hourly["time"]) if h[:13] >= now), 0)
        cols = [i for i in range(start + 1, min(start + 13, len(hourly["time"])), 2)][:6]
        cw = (self.W - 2 * pad) / max(1, len(cols))
        for k, i in enumerate(cols):
            cx = pad + k * cw + cw / 2
            g, _, hc = describe(hourly["weather_code"][i], hourly["is_day"][i])
            self.text(cx, y, hourly["time"][i][11:16], "small", "dim", "n")
            self.text(cx, y + 17, g, "icon", hc, "n")
            self.text(cx, y + 42, f"{round(hourly['temperature_2m'][i])}°", "body", "fg", "n")
            p = hourly["precipitation_probability"][i]
            self.text(cx, y + 60, f"{p}%" if p else "", "small", "sky", "n")
        y += 86

        # next days, with each day's range on the week's scale
        lo_all, hi_all = min(daily["temperature_2m_min"]), max(daily["temperature_2m_max"])
        span = max(1e-6, hi_all - lo_all)
        hot, warm = (86, 68) if self.cache.get("imperial") else (30, 20)
        bx1, bx2 = pad + 172, self.W - pad - 44
        for i, day in enumerate(daily["time"][:5]):
            row_y = y + i * 24
            name = "Today" if i == 0 else datetime.date.fromisoformat(day).strftime("%a %d")
            g, _, dc = describe(daily["weather_code"][i])
            lo, hi = daily["temperature_2m_min"][i], daily["temperature_2m_max"][i]
            p = daily["precipitation_probability_max"][i]
            self.text(pad, row_y, name, "body", "label")
            self.text(pad + 74, row_y - 2, g, "icon", dc)
            self.text(pad + 102, row_y + 1, f"{p}%" if p else "", "small", "sky")
            self.text(bx1 - 6, row_y, f"{round(lo)}°", "body", "dim", "ne")
            self.text(bx2 + 6, row_y, f"{round(hi)}°", "body", "fg", "nw")
            mid = row_y + 9
            self.rrect(bx1, mid - 3, bx2, mid + 3, 3, fill=T["track"], outline="")
            a = bx1 + (bx2 - bx1) * (lo - lo_all) / span
            b = bx1 + (bx2 - bx1) * (hi - lo_all) / span
            c = T["coral"] if hi >= hot else T["butter"] if hi >= warm else T["sky"]
            self.rrect(a, mid - 3, max(b, a + 6), mid + 3, 3, fill=c, outline="")


class BatteryPopup(Popup):
    STATUS = {"Charging": "charging", "Discharging": "on battery", "Full": "fully charged",
              "Not charging": "plugged in"}

    def __init__(self):
        super().__init__("battery", 390, 248)
        self.draw()

    def draw(self):
        cv, T, pad = self.cv, THEME, 18
        cv.delete("all")
        self.root.after(5000, self.draw)                 # keep the numbers live while open
        b = battery.state()
        if not b:
            self.text(self.W / 2, self.H / 2, "No battery found", "body", "label", "center")
            return
        self.text(pad, pad, "Battery", "title", "lavender")
        self.text(self.W - pad, pad + 3, self.STATUS.get(b["status"], b["status"].lower()), "small", "dim", "ne")
        self.divider(pad + 32, pad)

        y = pad + 44
        ic = self.text(pad, y - 4, b["glyph"], "bigicon", b["color"])
        t = self.text(self.cv.bbox(ic)[2] + 10, y, f"{b['pct']}%", "big", "fg")
        rx = self.cv.bbox(t)[2] + 18
        for i, line in enumerate((b["details"] or ["no details"])[:4]):
            self.text(rx, y + 1 + i * 16, line, "small", "fg" if i == 0 else "label")

        y += 76
        self.text(pad, y, "Power profile", "small", "dim")
        y += 20
        gap = 8
        w = (self.W - 2 * pad - 2 * gap) / 3
        for i, (key, glyph, name, c) in enumerate(battery.PROFILES):
            x1 = pad + i * (w + gap)
            on = key == b["profile"]
            box = self.rrect(x1, y, x1 + w, y + 40, 10, fill=T["track"] if on else T["card"],
                             outline=T[c] if on else T["edge"])
            label = self.text(x1 + w / 2, y + 20, f"{glyph} {name}", "bold" if on else "body",
                              c if on else "label", "center")
            self.button((box, label), lambda k=key: self.set_profile(k))

        link = self.text(pad, self.H - pad, "Power settings…", "small", "sky", "sw")
        self.button((link,), self.settings)

    def set_profile(self, key):
        subprocess.run([os.path.join(SCRIPTS, "actions.py"), "profile", key], timeout=10)
        self.draw()

    def settings(self):
        subprocess.Popen([os.path.join(SCRIPTS, "launch-app"), "--kcm", "kcm_powerdevilprofilesconfig"],
                         start_new_session=True)
        self.close()


POPUPS = {"calendar": CalendarPopup, "weather": WeatherPopup, "battery": BatteryPopup}

if __name__ == "__main__":
    kind = sys.argv[1] if len(sys.argv) > 1 else "calendar"
    if close_open(kind):
        sys.exit(0)
    POPUPS.get(kind, CalendarPopup)().show()
