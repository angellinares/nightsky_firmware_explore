#!/usr/bin/env python3
"""Decode / re-encode Strymon NightSky firmware .syx update files.

A firmware .syx is a stream of MIDI SysEx messages:

    F0 00 01 55 13 05 <cmd> 0C <7-bit-packed payload> F7

<cmd> is 0x43 for the fwu (controller / ARM) image and 0x42 for the fwd
(DSP) image. The payload is packed 8 bytes -> 7 data bytes: the first byte
of each group holds the high bit of each following byte, with data byte t
taking bit (6 - t) of that header byte.

An unpacked data message is:

    01 <c1> <off:u32 LE> <len:u32 LE> <chk:u32 LE> <len data bytes>

off is the byte offset of this chunk in the reconstructed image; the image
is the data chunks concatenated in offset order. There are also non-data
(marker) messages at the start/end whose unpacked byte[0] != 1.

    python syx_fw.py decode IN.syx OUT.bin      # write raw image
    python syx_fw.py info   IN.syx              # describe messages/blocks

This file only reshapes bytes we already own. It computes no new check
values and flashes nothing.
"""
from __future__ import annotations
import struct, sys


def split_sysex(raw: bytes) -> list[bytes]:
    out, i = [], 0
    while i < len(raw):
        if raw[i] != 0xF0:
            i += 1
            continue
        j = raw.index(0xF7, i)
        out.append(raw[i:j + 1])
        i = j + 1
    return out


def unpack7(payload: bytes) -> bytearray:
    """Undo the 8->7 high-bit packing. payload excludes F0..header and F7."""
    out = bytearray()
    for k in range(0, len(payload), 8):
        g = payload[k:k + 8]
        hi = g[0]
        for t, x in enumerate(g[1:]):
            out.append(x | (((hi >> (6 - t)) & 1) << 7))
    return out


HEADER_LEN = 8  # F0 00 01 55 13 05 <cmd> 0C


def iter_blocks(raw: bytes):
    """Yield (kind, decoded_bytes) for each message. kind is 'data' or 'marker'."""
    for m in split_sysex(raw):
        if len(m) <= HEADER_LEN + 1:
            yield "empty", m
            continue
        d = unpack7(m[HEADER_LEN:-1])
        yield ("data" if d and d[0] == 1 else "marker"), d


def decode(raw: bytes) -> bytes:
    img = bytearray()
    for kind, d in iter_blocks(raw):
        if kind != "data":
            continue
        _one, _c1, off, ln, _chk = struct.unpack_from("<BBIII", d, 0)
        data = bytes(d[14:14 + ln])
        if off != len(img):
            raise ValueError(f"gap: block at {off} but image is {len(img)}")
        img += data
    return bytes(img)


def info(raw: bytes) -> None:
    msgs = split_sysex(raw)
    print(f"{len(msgs)} SysEx messages")
    kinds = {}
    img_len = 0
    for kind, d in iter_blocks(raw):
        kinds[kind] = kinds.get(kind, 0) + 1
        if kind == "data":
            _o, _c, off, ln, chk = struct.unpack_from("<BBIII", d, 0)
            img_len = max(img_len, off + ln)
    print("message kinds:", kinds)
    print("reconstructed image length:", img_len)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "decode":
        raw = open(argv[2], "rb").read()
        img = decode(raw)
        open(argv[3], "wb").write(img)
        print(f"wrote {len(img)} bytes -> {argv[3]}")
    elif cmd == "info":
        info(open(argv[2], "rb").read())
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
