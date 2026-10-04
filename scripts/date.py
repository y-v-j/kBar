#!/usr/bin/python3
"""Date and time, ticking on the second. Click for the long format."""
import time

from common import Module, bold, fg, icon

m = Module("date", interval=1)


def render():
    if m.expanded:
        return f"{icon('󰃭', 'lavender')} {fg(time.strftime('%A, %d %B %Y'), 'label')}  {bold(time.strftime('%H:%M:%S'))}"
    return f"{icon('󰃭', 'lavender')} {fg(time.strftime('%a %d %b'), 'label')}  {bold(time.strftime('%H:%M'))}"


last = None
while True:
    line = render()
    if line != last:
        print(line, flush=True)
        last = line
    m.wait(1 - time.time() % 1 + 0.01)        # wake just after each second turns
