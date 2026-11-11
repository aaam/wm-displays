# wm-displays

A small graphical display-settings tool for **X11 window managers without a built-in
settings panel** (written for Window Maker). It is a Tk front end for
`xrandr` and works much like the Displays panel in GNOME.

Two files:

| File | Purpose |
|---|---|
| `wm-displays.py` | The tool (Python 3 + Tkinter, standard library only) |
| `wm-displays.sh` | Launcher: checks prerequisites, creates a virtualenv on first run, starts the tool |

## Why this tool

- **No desktop environment required.** It does not need Xfce, LXDE, GNOME or any of
  their libraries. The only requirements are Python 3, Tk and `xrandr`.
- **A bit more than lxrandr.** lxrandr is LXDE's deliberately minimal xrandr front end
  for changing resolution and quickly setting up an external monitor. wm-displays
  additionally **draws your displays graphically** on a canvas, where you drag them
  into position and they snap to each other's edges.

## Features

- Detect connected displays (re-runs `xrandr --query`, which polls the hardware)
- Draggable, edge-snapping layout of all enabled displays
- Per display: enable/disable, primary, resolution, refresh rate, orientation
- **Identify**: shows a large number on each screen for about 2.5 seconds
- **Mirror**: places all enabled displays at 0,0 using the largest resolution they share
- **Apply** with a GNOME-style 15-second *Keep changes / Revert* confirmation
- **Save for login**: writes `~/.config/wm-displays/apply.sh` and can append it to
  Window Maker's `~/GNUstep/Library/WindowMaker/autostart`

## Requirements

```sh
sudo apt install python3-tk x11-xserver-utils
```

`tkinter` cannot be installed with pip. It needs the system package `python3-tk`, which
a virtualenv created from the system `python3` inherits. The tool itself has no pip
dependencies, so the virtualenv only provides isolation.

## Usage

```sh
chmod +x wm-displays.sh
./wm-displays.sh              # creates the venv on first run, then starts the tool
# or, without the launcher:
python3 wm-displays.py
```

The virtualenv lives in `~/.local/share/wm-displays/venv`. Override it with
`WM_DISPLAYS_VENV=/some/path ./wm-displays.sh`.

In the window:

1. Click a display on the canvas (or pick it in the dropdown) and drag it into place.
2. Adjust enabled / primary / resolution / refresh rate / orientation.
3. Press **Apply**, then **Keep changes** within 15 seconds, or let it revert.
4. Optionally press **Save for login**.

## Status

- Verified on Ubuntu 22.04 with Window Maker and two displays: detection and the
  graphical layout, Mirror, Revert dialog, Identify and save for login.

## Limitations

- X11 only (xrandr); it does not work under Wayland.
- No fractional scaling. `xrandr --scale` only blurs the output.
- Dropping a display on top of another without snapping leaves them overlapping, which
  acts as mirroring (GNOME does not allow this).
- WindowMaker will not reposition your windows after saving.
  They have to be manually moved before they get out of the new display area.
- No automatic hotplug handling. Press **Detect** after connecting a monitor.
- **Save for login** stores the layout X is using *now* (not unapplied edits). Window
  Maker's `autostart` runs after the window manager has started. To apply the layout
  earlier, call `~/.config/wm-displays/apply.sh` from a file your session sources before
  the window manager (for example `~/.xsessionrc` on Debian/Ubuntu or ~/GNUstep/Library/WindowMaker/autostart).

## Troubleshooting

| Message | Fix |
|---|---|
| `DISPLAY is not set` | Start it from inside your X session |
| `xrandr not found` | `sudo apt install x11-xserver-utils` |
| `tkinter not found` | `sudo apt install python3-tk` |
| `venv creation failed` | `sudo apt install python3-venv` |
