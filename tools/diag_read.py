#!/usr/bin/env python3
"""Read the v9 knob-lane state on the NightSky over MIDI (CC 127).

    python tools/diag_read.py            # status + every lane
    python tools/diag_read.py status     # status only
    python tools/diag_read.py clear      # clear all lanes and flags (CC 127 = 0x46)

The CC goes out on all 16 channels because the pedal's MIDI channel is not
fixed. Quit the Strymon app first: it holds the MIDI ports while it runs.
Needs a debug build (tools/patch/build_patch.py --debug). Release builds
from v16 on have no MIDI readout.
"""
import sys, time
import rtmidi

HDR = [0xF0, 0x00, 0x01, 0x55, 0x13, 0x05]
KNOBS = ["REVERB", "DRY", "DEPTH", "INTERVAL", "LOW CUT", "LENGTH",
         "SPEED", "SHIMMER", "HIGH CUT"]          # slot 0..8 -> dsp id 1..8, 10


def open_ports():
    mo, mi = rtmidi.MidiOut(), rtmidi.MidiIn()
    oi = next((n for n, p in enumerate(mo.get_ports()) if "NightSky" in p), None)
    ii = next((n for n, p in enumerate(mi.get_ports()) if "NightSky" in p), None)
    if oi is None or ii is None:
        sys.exit("NightSky ports not found (is the Strymon app still open?)")
    mo.open_port(oi)
    mi.open_port(ii)
    mi.ignore_types(sysex=False, timing=True, active_sense=True)
    return mo, mi


def send_cc(mo, cc, value):
    """Send CC on all 16 channels: the pedal's MIDI channel is not fixed."""
    for ch in range(16):
        mo.send_message([0xB0 | ch, cc, value])
        time.sleep(0.003)


def ask(mo, mi, value, cmd, window=0.5):
    while mi.get_message():
        pass
    send_cc(mo, 0x7F, value)
    t0 = time.time()
    while time.time() - t0 < window:
        m = mi.get_message()
        if m and m[0][:7] == HDR + [cmd]:
            return m[0][7:-1]
        time.sleep(0.002)
    return None


def u14(hi, lo):
    return (hi << 7) | lo


def status(mo, mi):
    d = ask(mo, mi, 0x45, 0x45)
    if d is None or len(d) < 12:
        print("no status reply (not v9 firmware?)")
        return
    hasrec = d[4] | (d[5] << 7)
    baseset = d[6] | (d[7] << 7)
    margin = d[10] | (d[11] << 7)
    print(f"initialised          : {bool(d[9])}")
    print(f"live recording armed : {bool(d[0])}")
    print(f"chord held / used    : {d[1]} / {d[2]}")
    print(f"current step         : {d[3] + 1 if d[3] < 8 else 'none'}")
    print(f"guard                : {d[8]}")
    print(f"lanes with records   : {[KNOBS[s] for s in range(9) if hasrec >> s & 1] or 'none'}")
    print(f"lanes with base      : {[KNOBS[s] for s in range(9) if baseset >> s & 1] or 'none'}")
    print(f"stack margin         : {margin} bytes untouched above 0x2000ED00")
    if len(d) >= 14:
        print(f"armed LED            : {d[12]:#04x}, purple now: {bool(d[13])}")
    if len(d) >= 17:
        print(f"preset loads         : {d[14]} calls, last preset {u14(d[15], d[16])}")
    if len(d) >= 21:
        res = {0x6E: "skipped"}.get(d[18], d[18])      # 0xEE masked to 7 bits
        print(f"preset saves         : {d[17]} calls, last preset {u14(d[19], d[20])}, "
              f"tail write result {res}")
    if len(d) >= 22:
        why = {1: "lanes restored", 2: "no record, lanes cleared",
               3: "CRC bad, lanes cleared", 4: "preset changed, lanes cleared",
               5: "stock only (knob mode), lanes kept",
               6: "lane RAM not initialised"}.get(d[21], d[21])
        print(f"last lane restore    : {why}")
    if len(d) >= 26:
        print(f"stock knob-state ring: page {u14(d[22], d[23])}, "
              f"write counter (low 14 bits) {u14(d[24], d[25])}")
    if len(d) >= 29:
        res = {0x6E: "skipped"}.get(d[27], d[27])
        boot = {1: "lanes restored", 2: "no record", 3: "CRC bad",
                4: "counter differs (old record)", 7: "bad page",
                8: "not tried (clear command)"}.get(d[28], d[28])
        print(f"lane ring writes     : {d[26]}, last result {res}")
        print(f"power-up restore     : {boot}")


def lanes(mo, mi):
    print("\nlane       " + "  ".join(f"st{i + 1}" for i in range(8)) + "   base")
    for s in range(9):
        d = ask(mo, mi, 0x50 + s, 0x50)
        if d is None or len(d) < 21:
            print(f"{KNOBS[s]:<10} no reply")
            continue
        vals = [u14(d[1 + 2 * i], d[2 + 2 * i]) for i in range(8)]
        base = u14(d[17], d[18])
        cells = ["  - " if v == 0x3FFF else f"{v:4d}" for v in vals]
        b = f"{base:4d}" if d[20] else "   -"
        rec = "*" if d[19] else " "
        print(f"{KNOBS[s]:<9}{rec} " + " ".join(cells) + f"   {b}")
    print("(* = lane has records, - = no value)")


def main():
    mo, mi = open_ports()
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode == "clear":
        send_cc(mo, 0x7F, 0x46)
        print("clear sent")
        return
    if mode == "led":                      # diag_read.py led 33
        n = int(sys.argv[2], 0)
        send_cc(mo, 0x7E, n)
        print(f"armed LED set to {n:#04x}")
        return
    status(mo, mi)
    if mode != "status":
        lanes(mo, mi)


if __name__ == "__main__":
    main()
