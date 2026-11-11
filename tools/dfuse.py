#!/usr/bin/env python3
"""Parse an ST DfuSe (.dfu) file into its raw load images.

DfuSe layout:

    "DfuSe" u8:version u32:total_size u8:num_targets
    per target:
        "Target" u8:alt u32:named u8[255]:name u32:tgt_size u32:num_elems
        per element: u32:addr u32:size u8[size]:data
    suffix (16 bytes): firmware ver, PID, VID, "UFD", len, CRC32

    python dfuse.py info  IN.dfu
    python dfuse.py dump  IN.dfu OUT_PREFIX     # writes OUT_PREFIX_<addr>.bin

Read-only; writes only copies of bytes already in the file.
"""
from __future__ import annotations
import struct, sys


def parse(raw: bytes):
    assert raw[:5] == b"DfuSe", "not a DfuSe file"
    ver, total, ntgt = struct.unpack_from("<BIB", raw, 5)
    off = 11
    targets = []
    for _ in range(ntgt):
        sig, alt, named, name, tsize, nelem = struct.unpack_from("<6sBI255sII", raw, off)
        off += 274
        elems = []
        for _ in range(nelem):
            addr, size = struct.unpack_from("<II", raw, off)
            off += 8
            elems.append((addr, raw[off:off + size]))
            off += size
        targets.append({
            "alt": alt,
            "name": name.split(b"\0", 1)[0].decode("latin1"),
            "elements": elems,
        })
    suffix = raw[-16:]
    fw, pid, vid = struct.unpack_from("<HHH", suffix, 0)
    return {"version": ver, "pid": pid, "vid": vid, "fw": fw, "targets": targets}


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    cmd, path = argv[1], argv[2]
    d = parse(open(path, "rb").read())
    if cmd == "info":
        print(f"DfuSe v{d['version']}  VID {d['vid']:#06x}  PID {d['pid']:#06x}  fw {d['fw']:#06x}")
        for t in d["targets"]:
            print(f"  target alt={t['alt']} name={t['name']!r}")
            for addr, data in t["elements"]:
                print(f"    element @ {addr:#010x}  {len(data)} bytes")
    elif cmd == "dump":
        prefix = argv[3]
        for t in d["targets"]:
            for addr, data in t["elements"]:
                fn = f"{prefix}_{addr:08x}.bin"
                open(fn, "wb").write(data)
                print(f"wrote {len(data)} bytes @ {addr:#010x} -> {fn}")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
