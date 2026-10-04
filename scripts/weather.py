#!/usr/bin/python3
"""Current weather from Open-Meteo (free, no API key).

The location comes from [weather] in kbar.toml: a place name, "lat,lon", or
empty to locate by IP address once (cached). The forecast is cached for the
popup. Click for details; middle-click refreshes.
"""
import json
import os
import signal
import time
import urllib.parse
import urllib.request

from common import CACHE_DIR, Module, fg, icon

CACHE = os.path.join(CACHE_DIR, "weather.json")
PLACES = os.path.join(CACHE_DIR, "places.json")

# WMO weather code -> (day glyph, night glyph, description, colour)
CODES = {
    0: ("󰖙", "󰖔", "Clear", "butter"),
    1: ("󰖕", "󰼱", "Mostly clear", "butter"),
    2: ("󰖕", "󰼱", "Partly cloudy", "label"),
    3: ("󰖐", "󰖐", "Overcast", "label"),
    45: ("󰖑", "󰖑", "Fog", "dim"), 48: ("󰖑", "󰖑", "Freezing fog", "dim"),
    51: ("󰖗", "󰖗", "Light drizzle", "sky"), 53: ("󰖗", "󰖗", "Drizzle", "sky"),
    55: ("󰖗", "󰖗", "Heavy drizzle", "sky"), 56: ("󰖗", "󰖗", "Freezing drizzle", "sky"),
    57: ("󰖗", "󰖗", "Freezing drizzle", "sky"),
    61: ("󰖗", "󰖗", "Light rain", "sky"), 63: ("󰖖", "󰖖", "Rain", "sky"),
    65: ("󰖖", "󰖖", "Heavy rain", "sky"), 66: ("󰖗", "󰖗", "Freezing rain", "sky"),
    67: ("󰖖", "󰖖", "Freezing rain", "sky"),
    71: ("󰖘", "󰖘", "Light snow", "fg"), 73: ("󰖘", "󰖘", "Snow", "fg"),
    75: ("󰖘", "󰖘", "Heavy snow", "fg"), 77: ("󰖘", "󰖘", "Snow grains", "fg"),
    80: ("󰖖", "󰖖", "Showers", "sky"), 81: ("󰖖", "󰖖", "Showers", "sky"),
    82: ("󰖖", "󰖖", "Violent showers", "sky"),
    85: ("󰖘", "󰖘", "Snow showers", "fg"), 86: ("󰖘", "󰖘", "Snow showers", "fg"),
    95: ("󰖓", "󰖓", "Thunderstorm", "coral"),
    96: ("󰖒", "󰖒", "Thunderstorm, hail", "coral"), 99: ("󰖒", "󰖒", "Thunderstorm, hail", "coral"),
}


def describe(code, is_day=True):
    day, night, text, c = CODES.get(code, ("󰖐", "󰖐", "—", "label"))
    return (day if is_day else night), text, c


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "kbar"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save(path, data):
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def resolve(location):
    """(lat, lon, place name) for a place name, "lat,lon", or "" (by IP)."""
    places = load(PLACES, {})
    hit = places.get(location)
    if hit and (location or time.time() - hit.get("t", 0) < 86400):
        return hit["lat"], hit["lon"], hit["name"]
    parts = location.replace(" ", "").split(",")
    if len(parts) == 2 and all(p.lstrip("-").replace(".", "", 1).isdigit() for p in parts):
        lat, lon, name = float(parts[0]), float(parts[1]), location
    elif location:
        res = fetch_json("https://geocoding-api.open-meteo.com/v1/search?count=1&format=json&name="
                         + urllib.parse.quote(location)).get("results") or []
        if not res:
            raise ValueError(f"place not found: {location}")
        lat, lon, name = res[0]["latitude"], res[0]["longitude"], res[0]["name"]
    else:
        info = fetch_json("https://ipinfo.io/json")
        lat, lon = (float(v) for v in info["loc"].split(","))
        name = info.get("city") or "Here"
    places[location] = {"lat": lat, "lon": lon, "name": name, "t": time.time()}
    save(PLACES, places)
    return lat, lon, name


def update(cfg):
    w = cfg.get("weather", {})
    imperial = str(w.get("units", "metric")).lower() == "imperial"
    lat, lon, name = resolve(str(w.get("location", "")).strip())
    q = {
        "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 5,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,"
                   "wind_speed_10m,is_day",
        "hourly": "temperature_2m,weather_code,precipitation_probability,is_day",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
                 "sunrise,sunset",
        "temperature_unit": "fahrenheit" if imperial else "celsius",
        "wind_speed_unit": "mph" if imperial else "kmh",
    }
    data = fetch_json("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(q))
    save(CACHE, {"place": name, "fetched": time.time(), "imperial": imperial, "data": data})


def render(m):
    cached = load(CACHE, None)
    if not cached or time.time() - cached.get("fetched", 0) > 3 * 3600:
        return f"{icon('󰖑', 'dim')} {fg('--', 'dim')}"
    cur, units = cached["data"]["current"], cached["data"]["current_units"]
    glyph, text, c = describe(cur["weather_code"], cur.get("is_day", 1))
    out = f"{icon(glyph, c)} {round(cur['temperature_2m'])}°"
    if m.expanded:
        out += " " + fg(f"{text} · feels {round(cur['apparent_temperature'])}° · "
                        f"󰖎 {cur['relative_humidity_2m']}% · 󰖝 {round(cur['wind_speed_10m'])} "
                        f"{units['wind_speed_10m']}", "label")
    return out


def main():
    m = Module("weather", interval=60)
    next_fetch, last = 0, None
    while True:
        if time.time() >= next_fetch:
            try:
                update(m.cfg)
                next_fetch = time.time() + 60 * float(m.cfg.get("weather", {}).get("refresh_minutes", 15))
            except Exception:
                next_fetch = time.time() + 120        # offline: try again in two minutes
        line = render(m)
        if line != last:
            print(line, flush=True)
            last = line
        if m.wait(max(1, min(60, next_fetch - time.time()))) == signal.SIGUSR2:
            next_fetch = 0                             # middle-click / config change: fetch now


if __name__ == "__main__":
    main()
