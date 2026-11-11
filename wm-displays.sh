#!/usr/bin/env bash
# Launcher for wm-displays.py: creates a virtualenv on first run, then starts the tool.
# Override the venv location with WM_DISPLAYS_VENV=/some/path.
set -euo pipefail

here=$(dirname "$(readlink -f "$0")")
venv=${WM_DISPLAYS_VENV:-${XDG_DATA_HOME:-$HOME/.local/share}/wm-displays/venv}

die() { printf 'error: %s\n' "$*" >&2; exit 1; }

[ -n "${DISPLAY:-}" ]          || die "DISPLAY is not set (no X session?)"
command -v python3 >/dev/null  || die "python3 not found: sudo apt install python3"
command -v xrandr  >/dev/null  || die "xrandr not found: sudo apt install x11-xserver-utils"
python3 -c 'import tkinter' 2>/dev/null || die "tkinter not found: sudo apt install python3-tk"

if [ ! -x "$venv/bin/python" ]; then
    mkdir -p "$(dirname "$venv")"
    python3 -m venv "$venv" || { rm -rf "$venv"; die "venv creation failed: sudo apt install python3-venv"; }
fi

# wm-displays.py only uses the standard library, so nothing is pip-installed.
# Running the venv interpreter directly is equivalent to activating the venv.
exec "$venv/bin/python" "$here/wm-displays.py" "$@"
