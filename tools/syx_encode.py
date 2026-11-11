#!/usr/bin/env python3
"""Re-encode a raw controller image into a NightSky fwu .syx.

This module is the inverse of syx_fw.decode. It is checksum-complete:

- Per data block it writes chk = sum of the 256 data bytes read as
  little-endian uint32 words, mod 2**32. This value is verified against all
  373 blocks of the stock v1.07 fwu .syx.
- Marker messages (image start/end) are copied verbatim from a template .syx,
  so a rebuilt file matches the original byte for byte.

Self-integrity CRC-32 note: the stock .syx does NOT carry the word at
0x0803FFFC. The device bootloader computes that CRC after a flash. So the
.syx only needs correct per-block sums, not the integrity CRC.

    python syx_encode.py verify TEMPLATE.syx         # rebuild + byte-diff
    python syx_encode.py build  TEMPLATE.syx IMG.bin OUT.syx
"""
from __future__ import annotations
import struct, sys
sys.path.insert(0, __file__.rsplit("\\", 1)[0] if "\\" in __file__ else ".")
from syx_fw import split_sysex, unpack7, HEADER_LEN


def pack7(data: bytes) -> bytearray:
    """Inverse of syx_fw.unpack7: 7 data bytes -> 1 hi byte + 7 low-7-bit bytes."""
    out = bytearray()
    for k in range(0, len(data), 7):
        g = data[k:k + 7]
        hi = 0
        for t, b in enumerate(g):
            hi |= ((b >> 7) & 1) << (6 - t)
        out.append(hi)
        for b in g:
            out.append(b & 0x7F)
    return out


def block_checksum(data: bytes) -> int:
    """sum of data as little-endian uint32 words, mod 2**32 (len multiple of 4)."""
    total = 0
    for (w,) in struct.iter_unpack("<I", data):
        total += w
    return total & 0xFFFFFFFF


def build_data_record(c1: int, off: int, data: bytes) -> bytes:
    chk = block_checksum(data)
    return struct.pack("<BBIII", 1, c1, off, len(data), chk) + data


def rebuild(template: bytes, image: bytes | None = None) -> bytes:
    """Rebuild a .syx. If image is None, re-emit the template's own data.

    Marker/empty messages are copied verbatim. Data messages are regenerated
    from the image (or the template's decoded data) and re-packed with the
    same 8-byte SysEx header and trailing F7 as the template message.
    """
    out = bytearray()
    img_pos = 0
    for m in split_sysex(template):
        if len(m) <= HEADER_LEN + 1:
            out += m
            continue
        d = unpack7(m[HEADER_LEN:-1])
        if not d or d[0] != 1:
            out += m                     # marker: copy verbatim
            continue
        _one, c1, off, ln, _chk = struct.unpack_from("<BBIII", d, 0)
        if image is None:
            data = bytes(d[14:14 + ln])
        else:
            data = image[img_pos:img_pos + ln]
            img_pos += ln
        rec = build_data_record(c1, off, data)
        # preserve any trailing padding the original record carried after data
        tail = bytes(d[14 + ln:])
        packed = pack7(rec + tail)
        out += m[:HEADER_LEN] + bytes(packed) + b"\xF7"
    return bytes(out)


def _rewrite_marker(m: bytes, image_len: int, region_crc: int | None) -> bytes:
    """Rewrite a START/END marker's length and CRC fields, if it is one.

    A marker unpacks to 14 bytes: [type][c1][b2..b5][len:u32 LE][crc:u32 LE],
    with type 0 (start) or 2 (end). The length is the image byte count. The
    CRC is zlib.crc32 over the padded CRC region (image + 0xFF to 0x0803FFFC),
    the same value the device reports on MIDI command 0x31. Non-marker frames
    (short terminators) pass through unchanged. The length is always stamped.
    The CRC is stamped only when region_crc is given, else the template's CRC
    bytes are kept, so a stock rebuild reproduces the stock markers exactly.
    """
    if len(m) <= HEADER_LEN + 1:
        return m
    d = bytearray(unpack7(m[HEADER_LEN:-1]))
    if len(d) != 14 or d[0] not in (0, 2):
        return m
    d[6:10] = struct.pack("<I", image_len)
    if region_crc is not None:
        d[10:14] = struct.pack("<I", region_crc & 0xFFFFFFFF)
    pad = (-len(d)) % 7
    return m[:HEADER_LEN] + bytes(pack7(bytes(d) + b"\x00" * pad)) + b"\xF7"


def build_full(template: bytes, image: bytes, block: int = 256,
               region_crc: int | None = None) -> bytes:
    """Emit a full .syx for an ARBITRARY image (any length).

    Leading and trailing marker messages are regenerated so their length and
    CRC fields match the image (see _rewrite_marker). The image is chunked into
    `block`-byte data records with the template's data-message SysEx header.
    This supports a larger image, so a code cave above the stock end re-encodes
    to valid update messages.
    """
    msgs = split_sysex(template)
    # classify each template message
    def is_data(m):
        if len(m) <= HEADER_LEN + 1:
            return False
        d = unpack7(m[HEADER_LEN:-1])
        return bool(d) and d[0] == 1
    data_idx = [i for i, m in enumerate(msgs) if is_data(m)]
    first_d, last_d = data_idx[0], data_idx[-1]
    hdr = msgs[first_d][:HEADER_LEN]          # F0 00 01 55 13 05 <cmd> 0C
    # c1 from the template's first data record
    d0 = unpack7(msgs[first_d][HEADER_LEN:-1])
    c1 = d0[1]
    out = bytearray()
    for m in msgs[:first_d]:                   # leading markers
        out += _rewrite_marker(m, len(image), region_crc)
    off = 0
    while off < len(image):
        data = image[off:off + block]
        rec = build_data_record(c1, off, data)
        # Stock pads each record with zero bytes so (header+data+pad) is a
        # multiple of 7. The 7-bit packer then emits only full 8-byte groups,
        # matching the stock framing byte for byte (3 zeros for a 256- or
        # 200-byte block). Replicate it for any block length.
        pad = (-len(rec)) % 7
        out += hdr + bytes(pack7(rec + b"\x00" * pad)) + b"\xF7"
        off += len(data)
    for m in msgs[last_d + 1:]:                # trailing markers
        out += _rewrite_marker(m, len(image), region_crc)
    return bytes(out)


def main(argv):
    if len(argv) >= 3 and argv[1] == "verify":
        tpl = open(argv[2], "rb").read()
        rebuilt = rebuild(tpl, image=None)
        same = rebuilt == tpl
        print(f"template {len(tpl)} bytes, rebuilt {len(rebuilt)} bytes")
        print("BYTE-FOR-BYTE IDENTICAL" if same else "MISMATCH")
        if not same:
            n = min(len(tpl), len(rebuilt))
            for i in range(n):
                if tpl[i] != rebuilt[i]:
                    print(f"first diff at {i}: tpl={tpl[i]:02X} rebuilt={rebuilt[i]:02X}")
                    break
            if len(tpl) != len(rebuilt):
                print(f"length differs: {len(tpl)} vs {len(rebuilt)}")
        return 0 if same else 1
    if len(argv) >= 5 and argv[1] == "build":
        tpl = open(argv[2], "rb").read()
        img = open(argv[3], "rb").read()
        out = rebuild(tpl, image=img)
        open(argv[4], "wb").write(out)
        print(f"wrote {len(out)} bytes -> {argv[4]}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
