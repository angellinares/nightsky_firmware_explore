#!/usr/bin/env python3
"""Read the unused tail of preset slots on the NightSky (read only).

    python tools/tail_read.py 0 1 2 15      # presets 0, 1, 2 and 15
    python tools/tail_read.py 0 -v          # also print a hex dump

Each preset slot in the external flash is 0x800 bytes. Stock uses 0x4FC.
This tool reads 0x4FC..0x81B (25 chunks of 32 bytes, the last chunk runs
into the next slot) with CC 124 = preset and CC 125 = chunk. Presets 0..127
only. Needs a debug build (build_patch.py --debug). Quit the Strymon app first.
"""
import binascii, struct, sys, time
from diag_read import open_ports, send_cc, HDR

SLOT_TAIL = 0x4FC
CHUNKS = 25


def read_tail(mo, mi, preset):
    send_cc(mo, 0x7C, preset)
    data = bytearray()
    for c in range(CHUNKS):
        while mi.get_message():
            pass
        d = None
        for _ in range(3):
            d = ask_cc(mo, mi, c)
            if d is not None:
                break
        if d is None or len(d) < 66 or d[1] != c:
            sys.exit(f"preset {preset}: no reply for chunk {c}")
        data += bytes((d[2 + 2 * i] << 4) | d[3 + 2 * i] for i in range(32))
    return bytes(data)


def ask_cc(mo, mi, chunk):
    send_cc(mo, 0x7D, chunk)
    t0 = time.time()
    while time.time() - t0 < 0.5:
        m = mi.get_message()
        if m and m[0][:7] == HDR + [0x60]:
            return m[0][7:-1]          # preset, chunk, then 64 nibbles
        time.sleep(0.002)
    return None


def main():
    args = [a for a in sys.argv[1:] if a != "-v"]
    verbose = "-v" in sys.argv
    presets = [int(a, 0) for a in args] or [0]
    mo, mi = open_ports()
    for p in presets:
        t = read_tail(mo, mi, p)
        own = t[:0x800 - SLOT_TAIL]                    # 772 bytes of this slot
        ff = sum(b == 0xFF for b in own)
        print(f"preset {p:3d}: {ff}/{len(own)} bytes are 0xFF in 0x4FC..0x7FF")
        if verbose or ff != len(own):
            for off in range(0, len(own), 16):
                row = own[off:off + 16]
                if verbose or any(b != 0xFF for b in row):
                    print(f"   +{SLOT_TAIL + off:03X}: {row.hex(' ')}")
        print_record(own[REC_OFF - SLOT_TAIL:REC_OFF - SLOT_TAIL + 0xC0])


REC_OFF = 0x700
KNOBS = ["REVERB", "DRY", "DEPTH", "INTERVAL", "LOW CUT", "LENGTH",
         "SPEED", "SHIMMER", "HIGH CUT"]


def print_record(r):
    """Decode the lane record at slot + 0x700 (persistence step 2)."""
    magic, ver, csum = struct.unpack_from("<HHI", r, 0)
    if magic != 0x4C4E:
        print("   no lane record")
        return
    crc = struct.unpack_from("<H", r, 0xB2)[0]
    ok = binascii.crc_hqx(r[:0xB2], 0xFFFF) == crc
    ram = r[8:8 + 0xAA]
    hasrec, baseset = struct.unpack_from("<HH", ram, 0xA6)
    print(f"   lane record v{ver}, preset checksum {csum:08X}, CRC {'ok' if ok else 'BAD'}")
    print(f"   lanes with records: {[KNOBS[s] for s in range(9) if hasrec >> s & 1] or 'none'}")
    for s in range(9):
        if hasrec >> s & 1:
            vals = struct.unpack_from("<8H", ram, s * 16)
            print(f"     {KNOBS[s]:<9}" + " ".join("  - " if v == 0xFFFF else f"{v:4d}" for v in vals))


if __name__ == "__main__":
    main()
