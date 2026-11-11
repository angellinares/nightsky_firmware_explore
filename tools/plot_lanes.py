#!/usr/bin/env python3
"""Plot the v9 knob lanes on the NightSky as a figure, one row per knob.

    python tools/plot_lanes.py [out.png]

Reads the lanes over MIDI (CC 127, same readout as diag_read.py), so quit the
Strymon app first. Solid bar = recorded value. Pale bar = no record, the step
plays the knob's base level. No bar = the pedal sends nothing on that step.
"""
import os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from diag_read import open_ports, ask, u14, KNOBS

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e4e3df"
SERIES = "#2a78d6"     # categorical slot 1
BASE_TINT = "#c9dcf4"  # same hue, light step: "plays the base level"
UNSET = 0x3FFF


def read_lanes():
    mo, mi = open_ports()
    st = ask(mo, mi, 0x45, 0x45)
    lanes = []
    for s in range(9):
        d = ask(mo, mi, 0x50 + s, 0x50)
        if d is None or len(d) < 21:
            sys.exit(f"no reply for lane {KNOBS[s]}")
        vals = [u14(d[1 + 2 * i], d[2 + 2 * i]) for i in range(8)]
        lanes.append({"name": KNOBS[s], "vals": vals,
                      "base": u14(d[17], d[18]) if d[20] else None,
                      "has": bool(d[19])})
    armed = bool(st and st[0])
    cur = st[3] if st and st[3] < 8 else None
    return lanes, armed, cur


def plot(lanes, armed, cur, out):
    active = [l for l in lanes if l["has"]]
    idle = [l["name"] for l in lanes if not l["has"]]
    rows = max(len(active), 1)
    fig, axes = plt.subplots(rows, 1, figsize=(8, 1.35 * rows + 1.2),
                             sharex=True, squeeze=False)
    fig.patch.set_facecolor(SURFACE)
    steps = list(range(1, 9))
    for ax, lane in zip(axes[:, 0], active or [None]):
        ax.set_facecolor(SURFACE)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(GRID)
        ax.tick_params(colors=INK2, labelsize=8, length=0)
        ax.yaxis.grid(True, color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        if lane is None:
            ax.text(0.5, 0.5, "No lane holds a recording yet", ha="center",
                    va="center", color=INK2, transform=ax.transAxes)
            ax.set_yticks([])
            continue
        top = max([v for v in lane["vals"] if v != UNSET] + [lane["base"] or 0, 1])
        for x, v in zip(steps, lane["vals"]):
            if v != UNSET:
                ax.bar(x, v, width=0.72, color=SERIES, zorder=3)
                ax.text(x, v + top * 0.04, str(v), ha="center", va="bottom",
                        fontsize=8, color=INK, zorder=4)
            elif lane["base"] is not None:
                ax.bar(x, lane["base"], width=0.72, color=BASE_TINT, zorder=3)
        ax.set_ylim(0, top * 1.28)
        ax.set_yticks([0, top])
        base_txt = f"base {lane['base']}" if lane["base"] is not None else "no base"
        ax.set_ylabel(f"{lane['name']}\n{base_txt}", rotation=0, ha="right",
                      va="center", fontsize=9, color=INK, labelpad=10)
        if cur is not None:
            ax.axvspan(cur + 0.5, cur + 1.5, color=GRID, alpha=0.5, zorder=1)
    axes[-1, 0].set_xticks(steps)
    axes[-1, 0].set_xticklabels([f"step {s}" for s in steps])
    rec = "on" if armed else "off"
    fig.suptitle(f"NightSky knob lanes per step  (live recording {rec})",
                 x=0.02, ha="left", fontsize=11, color=INK, y=0.995)
    note = ("Dark bar = recorded value.  Pale bar = no record, plays the base level."
            + ("  Grey column = playing step." if cur is not None else ""))
    if idle:
        note += "\nNo records: " + ", ".join(idle) + "."
    fig.text(0.02, 0.005, note, fontsize=8, color=INK2, ha="left", va="bottom")
    fig.tight_layout(rect=(0, 0.06 if idle else 0.04, 1, 0.96))
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    print(f"wrote {out}")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "out", "lanes.png")
    lanes, armed, cur = read_lanes()
    plot(lanes, armed, cur, os.path.abspath(out))
