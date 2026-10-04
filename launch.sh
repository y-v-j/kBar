#!/bin/sh
# Start (or restart) kBar.
#
# It runs as its own systemd user service, so it gets the desktop session's
# environment no matter where this is run from. Stop it with
#   systemctl --user stop kbar
systemctl --user stop kbar.service 2>/dev/null
systemctl --user reset-failed kbar.service 2>/dev/null
exec systemd-run --user --quiet --collect --unit=kbar \
  --description="kBar" "$(dirname "$(realpath "$0")")/scripts/run-bar"
