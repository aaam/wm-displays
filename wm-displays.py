#!/usr/bin/env python3

"""wm-displays - GNOME-style display settings for X11 / Window Maker (xrandr backend).

Needs: python3-tk and x11-xserver-utils
    sudo apt install python3-tk x11-xserver-utils
"""

import copy
import os
import re
import shlex
import shutil
import subprocess
import sys

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except ImportError:
    sys.exit("tkinter is missing: sudo apt install python3-tk")

ROTATIONS = ["normal", "left", "right", "inverted"]
CONF_DIR = os.path.expanduser("~/.config/wm-displays")
SCRIPT = os.path.join(CONF_DIR, "apply.sh")
AUTOSTART = os.path.expanduser("~/GNUstep/Library/WindowMaker/autostart")
AUTOSTART_LINE = '"$HOME/.config/wm-displays/apply.sh" &'

HDR = re.compile(r"^(\S+) (connected|disconnected)(?: (primary))?"
                 r"(?: (\d+)x(\d+)\+(\d+)\+(\d+))?(?: (normal|left|right|inverted))?")
MODE = re.compile(r"^\s+(\d+)x(\d+)(i?)\s+(.*)$")
RATE = re.compile(r"(\d+(?:\.\d+)?)\s?([*+]*)")


class Output:
    def __init__(self, name):
        self.name = name
        self.modes = {}        # (w, h, interlaced) -> [rate strings]
        self.preferred = None
        self.cur = None        # (mode, rate) active right now
        self.enabled = False
        self.mode = self.rate = None
        self.rot = "normal"
        self.x = self.y = 0
        self.primary = False

    @staticmethod
    def label(m):
        return f"{m[0]}x{m[1]}{'i' if m[2] else ''}"

    def size(self):
        w, h = self.mode[0], self.mode[1]
        return (h, w) if self.rot in ("left", "right") else (w, h)


def best(rates):
    return max(rates, key=float)


def query():
    """Run `xrandr --query` (polls the hardware) and return connected outputs."""
    text = subprocess.run(["xrandr", "--query"], capture_output=True,
                          text=True, check=True).stdout
    outs, cur, connected = [], None, False
    for line in text.splitlines():
        h = HDR.match(line)
        if h:
            connected = h.group(2) == "connected"
            cur = Output(h.group(1))
            cur.primary = bool(h.group(3))
            if h.group(4):
                cur.enabled = True
                cur.x, cur.y = int(h.group(6)), int(h.group(7))
            cur.rot = h.group(8) or "normal"
            if connected:
                outs.append(cur)
            continue
        m = MODE.match(line)
        if m and cur is not None and connected:
            key = (int(m.group(1)), int(m.group(2)), bool(m.group(3)))
            rates = []
            for val, flags in RATE.findall(m.group(4)):
                rates.append(val)
                if "*" in flags:
                    cur.cur = (key, val)
                if "+" in flags and cur.preferred is None:
                    cur.preferred = key
            cur.modes[key] = rates
    outs = [o for o in outs if o.modes]
    for o in outs:
        o.mode = o.cur[0] if o.cur else (o.preferred or next(iter(o.modes)))
        o.rate = o.cur[1] if o.cur else best(o.modes[o.mode])
        if not o.cur:
            o.enabled = False
    return outs


def build_cmd(outputs):
    cmd = ["xrandr"]
    for o in outputs:
        cmd += ["--output", o.name]
        if not o.enabled:
            cmd.append("--off")
            continue
        cmd += ["--mode", Output.label(o.mode), "--rate", o.rate,
                "--pos", f"{o.x}x{o.y}", "--rotate", o.rot]
        if o.primary:
            cmd.append("--primary")
    if not any(o.enabled and o.primary for o in outputs):
        cmd.append("--noprimary")
    return cmd


def overlaps(a, b):
    aw, ah = a.size()
    bw, bh = b.size()
    return a.x < b.x + bw and b.x < a.x + aw and a.y < b.y + bh and b.y < a.y + ah


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Display Settings")
        self.geometry("860x580")
        self.outputs, self.base = [], []
        self.sel = None
        self.drag = None
        self.frozen = None
        self._ui()
        self.detect()

    # ---------------------------------------------------------------- UI
    def _ui(self):
        c = self.canvas = tk.Canvas(self, bg="#2b2b2b", highlightthickness=0)
        c.pack(fill="both", expand=True, padx=8, pady=8)
        c.bind("<Configure>", lambda e: self.draw())
        c.bind("<ButtonPress-1>", self.on_press)
        c.bind("<B1-Motion>", self.on_drag)
        c.bind("<ButtonRelease-1>", self.on_release)

        f = ttk.LabelFrame(self, text="Display", padding=8)
        f.pack(fill="x", padx=8)
        self.v_en, self.v_pr = tk.BooleanVar(), tk.BooleanVar()
        self.v_res, self.v_rate, self.v_rot = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.c_out = ttk.Combobox(f, state="readonly", width=24)
        self.c_out.grid(row=0, column=0, columnspan=2, sticky="w")
        self.c_out.bind("<<ComboboxSelected>>", lambda e: self.select(self.outputs[self.c_out.current()]))
        ttk.Checkbutton(f, text="Enabled", variable=self.v_en,
                        command=self.on_enable).grid(row=0, column=2, padx=10)
        ttk.Checkbutton(f, text="Primary", variable=self.v_pr,
                        command=self.on_primary).grid(row=0, column=3)
        self.c_res = self._combo(f, "Resolution", self.v_res, 0, self.on_res)
        self.c_rate = self._combo(f, "Refresh (Hz)", self.v_rate, 1, self.on_rate)
        self.c_rot = self._combo(f, "Orientation", self.v_rot, 2, self.on_rot, ROTATIONS)

        bar = ttk.Frame(self, padding=8)
        bar.pack(fill="x")
        for text, cmd, side in (("Detect", self.detect, "left"),
                                ("Identify", self.identify, "left"),
                                ("Mirror", self.mirror, "left"),
                                ("Apply", self.apply, "right"),
                                ("Save for login", self.save, "right")):
            ttk.Button(bar, text=text, command=cmd).pack(side=side, padx=3)

    def _combo(self, parent, label, var, col, cb, values=()):
        ttk.Label(parent, text=label).grid(row=1, column=col * 2, sticky="e", pady=6, padx=(0, 4))
        cb_ = ttk.Combobox(parent, textvariable=var, state="readonly", width=12, values=list(values))
        cb_.grid(row=1, column=col * 2 + 1, sticky="w", padx=(0, 12))
        cb_.bind("<<ComboboxSelected>>", lambda e: cb())
        return cb_

    # ------------------------------------------------------------- model
    def active(self):
        return [o for o in self.outputs if o.enabled]

    def detect(self):
        try:
            self.outputs = query()
        except (OSError, subprocess.CalledProcessError) as e:
            messagebox.showerror("xrandr failed", str(e))
            self.outputs = []
        self.base = copy.deepcopy(self.outputs)   # what X is really doing now
        self.sel = next((o for o in self.outputs if o.primary), None) or \
            (self.outputs[0] if self.outputs else None)
        self.refresh()

    def select(self, o):
        self.sel = o
        self.refresh()

    def normalise(self):
        act = self.active()
        if act:
            mx, my = min(o.x for o in act), min(o.y for o in act)
            for o in act:
                o.x -= mx
                o.y -= my

    def resolve(self, o):
        """After a size change, push overlapping neighbours out of the way."""
        for p in self.active():
            if p is not o and overlaps(o, p):
                if p.x >= o.x:
                    p.x = o.x + o.size()[0]
                else:
                    o.x = p.x + p.size()[0]

    def refresh(self):
        self.c_out["values"] = [f"{i + 1}: {o.name}{'' if o.enabled else ' (off)'}"
                                for i, o in enumerate(self.outputs)]
        o = self.sel
        if o:
            self.c_out.current(self.outputs.index(o))
            self.v_en.set(o.enabled)
            self.v_pr.set(o.primary)
            keys = sorted(o.modes, key=lambda k: (k[0] * k[1], k[0]), reverse=True)
            self.c_res["values"] = [Output.label(k) for k in keys]
            self.v_res.set(Output.label(o.mode))
            self.c_rate["values"] = o.modes[o.mode]
            self.v_rate.set(o.rate)
            self.v_rot.set(o.rot)
        self.draw()

    # ---------------------------------------------------------- handlers
    def on_enable(self):
        o = self.sel
        if not o:
            return
        want = self.v_en.get()
        if not want and self.active() == [o]:
            self.v_en.set(True)
            messagebox.showinfo("Display Settings", "At least one display must stay enabled.")
            return
        if want:
            others = self.active()
            o.x = max((p.x + p.size()[0] for p in others), default=0)
            o.y = 0
        else:
            o.primary = False
        o.enabled = want
        self.normalise()
        self.refresh()

    def on_primary(self):
        o = self.sel
        if not o or not o.enabled:
            self.v_pr.set(False)
            return
        for p in self.outputs:
            p.primary = False
        o.primary = self.v_pr.get()
        self.refresh()

    def on_res(self):
        o = self.sel
        o.mode = next(k for k in o.modes if Output.label(k) == self.v_res.get())
        if o.rate not in o.modes[o.mode]:
            o.rate = best(o.modes[o.mode])
        if o.enabled:
            self.resolve(o)
            self.normalise()
        self.refresh()

    def on_rate(self):
        self.sel.rate = self.v_rate.get()

    def on_rot(self):
        o = self.sel
        o.rot = self.v_rot.get()
        if o.enabled:
            self.resolve(o)
            self.normalise()
        self.refresh()

    def mirror(self):
        act = self.active()
        if len(act) < 2:
            return
        common = set.intersection(*(set(o.modes) for o in act))
        if not common:
            messagebox.showerror("Mirror", "The enabled displays share no common resolution.")
            return
        m = max(common, key=lambda k: k[0] * k[1])
        for o in act:
            o.mode, o.rate, o.x, o.y, o.rot = m, best(o.modes[m]), 0, 0, "normal"
        self.refresh()

    # ------------------------------------------------------------ canvas
    def tf(self):
        act = self.active()
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        if not act:
            return 1.0, 0.0, 0.0
        x0, y0 = min(o.x for o in act), min(o.y for o in act)
        x1 = max(o.x + o.size()[0] for o in act)
        y1 = max(o.y + o.size()[1] for o in act)
        bw, bh = x1 - x0, y1 - y0
        s = min(cw / (bw * 1.6), ch / (bh * 1.6))      # spare room to drag around
        return s, cw / 2 - (x0 + bw / 2) * s, ch / 2 - (y0 + bh / 2) * s

    def draw(self):
        c = self.canvas
        c.delete("all")
        s, ox, oy = self.frozen or self.tf()
        for i, o in enumerate(self.outputs):
            if not o.enabled:
                continue
            w, h = o.size()
            x, y = ox + o.x * s, oy + o.y * s
            sel = o is self.sel
            c.create_rectangle(x, y, x + w * s, y + h * s,
                               fill="#4a78b5" if sel else "#555555",
                               outline="#ffd24a" if sel else "#999999", width=3 if sel else 1)
            c.create_text(x + w * s / 2, y + h * s / 2, fill="white", justify="center",
                          text=f"{i + 1}\n{o.name}\n{w}x{h}")
            if o.primary:
                c.create_rectangle(x, y, x + w * s, y + 14, fill="#222222", outline="")
                c.create_text(x + 6, y + 7, text="primary", anchor="w", fill="white", font=("sans", 8))

    def hit(self, ex, ey):
        s, ox, oy = self.frozen
        for o in reversed(self.active()):
            w, h = o.size()
            if ox + o.x * s <= ex <= ox + (o.x + w) * s and oy + o.y * s <= ey <= oy + (o.y + h) * s:
                return o
        return None

    def on_press(self, e):
        self.frozen = self.tf()          # keep scale/origin stable while dragging
        o = self.hit(e.x, e.y)
        if o:
            self.sel = o
            self.drag = (o, e.x, e.y, o.x, o.y)
            self.refresh()
        else:
            self.frozen = None

    def on_drag(self, e):
        if not self.drag:
            return
        o, sx, sy, x0, y0 = self.drag
        s = self.frozen[0]
        o.x = round(x0 + (e.x - sx) / s)
        o.y = round(y0 + (e.y - sy) / s)
        self.snap(o, 30 / s)
        self.draw()

    def on_release(self, e):
        if self.drag:
            self.normalise()
        self.drag = self.frozen = None
        self.draw()

    def snap(self, o, th):
        w, h = o.size()
        best_ = None
        for p in self.active():
            if p is o:
                continue
            pw, ph = p.size()
            for nx in (p.x + pw, p.x - w):                       # abut left/right
                d = abs(o.x - nx)
                if d < th and (best_ is None or d < best_[0]):
                    ny = min((p.y, p.y + ph - h), key=lambda v: abs(v - o.y))
                    best_ = (d, nx, ny if abs(ny - o.y) < th else o.y)
            for ny in (p.y + ph, p.y - h):                       # abut top/bottom
                d = abs(o.y - ny)
                if d < th and (best_ is None or d < best_[0]):
                    nx = min((p.x, p.x + pw - w), key=lambda v: abs(v - o.x))
                    best_ = (d, nx if abs(nx - o.x) < th else o.x, ny)
        if best_:
            o.x, o.y = best_[1], best_[2]

    # ----------------------------------------------------------- actions
    def identify(self):
        for i, o in enumerate(self.base):
            if not o.enabled:
                continue
            w = tk.Toplevel(self)
            w.overrideredirect(True)
            w.geometry(f"220x140+{o.x + 40}+{o.y + 40}")
            tk.Label(w, text=str(i + 1), font=("sans", 72, "bold"),
                     bg="#222222", fg="white").pack(fill="both", expand=True)
            w.after(2500, w.destroy)

    def apply(self):
        if not self.active():
            return
        cmd = build_cmd(self.outputs)
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            messagebox.showerror("xrandr failed", (r.stderr or "unknown error") + "\n\n" + shlex.join(cmd))
            return
        self.confirm(self.base)

    def confirm(self, old):
        """GNOME-style: revert automatically unless the user keeps the change."""
        d = tk.Toplevel(self)
        d.title("Keep display settings?")
        d.transient(self)
        lbl = ttk.Label(d, padding=14, justify="center")
        lbl.pack()
        left, done = [15], [False]

        def finish(keep):
            if done[0]:
                return
            done[0] = True
            if not keep:
                subprocess.run(build_cmd(old), capture_output=True)
            d.destroy()
            self.detect()

        def tick():
            if done[0]:
                return
            if left[0] <= 0:
                finish(False)
                return
            lbl.config(text=f"Display settings changed.\nReverting in {left[0]} s unless you keep them.")
            left[0] -= 1
            d.after(1000, tick)

        bf = ttk.Frame(d)
        bf.pack(pady=(0, 12))
        ttk.Button(bf, text="Keep changes", command=lambda: finish(True)).pack(side="left", padx=6)
        ttk.Button(bf, text="Revert", command=lambda: finish(False)).pack(side="left", padx=6)
        d.protocol("WM_DELETE_WINDOW", lambda: finish(False))
        tick()

    def save(self):
        """Persist the layout X is using now (not unapplied edits)."""
        os.makedirs(CONF_DIR, exist_ok=True)
        with open(SCRIPT, "w") as f:
            f.write("#!/bin/sh\n# Generated by wm-displays\nexec " + shlex.join(build_cmd(self.base)) + "\n")
        os.chmod(SCRIPT, 0o755)
        if not messagebox.askyesno("Run at Window Maker start?",
                                   f"Saved {SCRIPT}\n\nAlso add it to\n{AUTOSTART} ?"):
            return
        os.makedirs(os.path.dirname(AUTOSTART), exist_ok=True)
        text = open(AUTOSTART).read() if os.path.exists(AUTOSTART) else "#!/bin/sh\n"
        if "wm-displays/apply.sh" not in text:
            with open(AUTOSTART, "w") as f:
                f.write(text.rstrip("\n") + "\n" + AUTOSTART_LINE + "\n")
        os.chmod(AUTOSTART, os.stat(AUTOSTART).st_mode | 0o111)


if __name__ == "__main__":
    if not shutil.which("xrandr"):
        sys.exit("xrandr not found: sudo apt install x11-xserver-utils")
    App().mainloop()
