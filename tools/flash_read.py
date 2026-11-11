#!/usr/bin/env python3
"""Read the NightSky external SPI flash over MIDI (read only).

    python tools/flash_read.py dump 0x0F0000 0x200      # hex dump
    python tools/flash_read.py scan 0x130000 0x170000   # list non-0xFF areas

CC 121/122/123 set the address (bits 20..14, 13..7, 6..0). CC 120 = c reads
32 bytes at address + c * 32 (c = 0..127, one 4 KB window per address).
Needs a debug build (build_patch.py --debug). Quit the Strymon app first.
"""
import sys, time
from diag_read import open_ports, send_cc, HDR

WIN = 0x1000


def set_addr(mo, addr):
    send_cc(mo, 0x79, (addr >> 14) & 0x7F)
    send_cc(mo, 0x7A, (addr >> 7) & 0x7F)
    send_cc(mo, 0x7B, addr & 0x7F)


def chunk(mo, mi, c):
    for _ in range(3):
        while mi.get_message():
            pass
        send_cc(mo, 0x78, c)
        t0 = time.time()
        while time.time() - t0 < 0.5:
            m = mi.get_message()
            if m and m[0][:7] == HDR + [0x64]:
                d = m[0][7:-1]
                if len(d) >= 65 and d[0] == c:
                    return bytes((d[1 + 2 * i] << 4) | d[2 + 2 * i] for i in range(32))
            time.sleep(0.001)
    sys.exit(f"no reply for chunk {c}")


def read(mo, mi, start, length):
    out = bytearray()
    a = start
    while a < start + length:
        base = a & ~(WIN - 1)
        set_addr(mo, base)
        time.sleep(0.01)
        while a < min(base + WIN, start + length):
            c = (a - base) // 32
            out += chunk(mo, mi, c)
            a = base + (c + 1) * 32
    return bytes(out[:length])


def main():
    if len(sys.argv) < 4 or sys.argv[1] not in ("dump", "scan"):
        sys.exit(__doc__)
    mode, a, b = sys.argv[1], int(sys.argv[2], 0) & ~31, int(sys.argv[3], 0)
    mo, mi = open_ports()
    if mode == "dump":
        data = read(mo, mi, a, b)
        for off in range(0, len(data), 16):
            print(f"{a + off:06X}: {data[off:off + 16].hex(' ')}")
        return
    run = None                                  # scan a..b, print non-FF runs
    for base in range(a, b, WIN):
        data = read(mo, mi, base, min(WIN, b - base))
        for i in range(0, len(data), 32):
            used = any(x != 0xFF for x in data[i:i + 32])
            if used and run is None:
                run = base + i
            if not used and run is not None:
                print(f"used {run:06X}..{base + i - 1:06X}")
                run = None
        print(f"  scanned to {base + len(data):06X}", end="\r")
    if run is not None:
        print(f"used {run:06X}..{b - 1:06X}")
    print(f"\nscan {a:06X}..{b - 1:06X} done")


if __name__ == "__main__":
    main()
