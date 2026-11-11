#!/usr/bin/env python3
"""Build the reverb-per-step (live) patched NightSky controller image + .syx.

Steps:
 1. Assemble cave.s (WSL arm-none-eabi-gcc) -> flat blob + T1/T2 offsets.
 2. Splice the cave at CAVE_OFF and patch the two hook sites with bl.
 3. Rebuild a flashable .syx with tools/syx_encode.build_full.
 4. Verify: .syx decodes back to the patched image; disassemble patched sites.

Nothing is flashed. Output lands in out/.
"""
import os, sys, subprocess, struct, zlib
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import syx_fw, syx_encode
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

IMG_BASE   = 0x0800C000
STOCK_BIN  = os.path.join(ROOT, "out", "fwu_v107.bin")
STOCK_SYX  = os.path.join(ROOT, "firmware-backup", "v1.07", "1305_0107_fwu.syx")
OUT_BIN    = os.path.join(ROOT, "out", "fwu_v107_revstep.bin")
OUT_SYX    = os.path.join(ROOT, "out", "fwu_v107_revstep.syx")

CAVE_ADDR  = 0x08023500
CAVE_OFF   = CAVE_ADDR - IMG_BASE            # 0x17500
HOOK_PLAY  = 0x08019E3C                        # displaces bl 0x08019B7C
HOOK_REC   = 0x080132A2                        # dsp_send_param entry; displaces ldr r3,[..];ldrb r3,[r3]
HOOK_CC    = 0x080144F8                        # CC handler entry (b.w); displaces cmp r0,#0x51; push {r4-r6,lr}
HOOK_Q     = 0x08013230                        # DSP funnel entry (b.w); displaces ldr r3,[..]; ldrb r3,[r3]
HOOK_POLL  = 0x08015C48                        # param_input_router entry (b.w); displaces push.w {r4-r11,lr}
HOOK_LOAD  = 0x080121C4                        # FUN_080121c4 preset load entry (b.w); displaces push {r3-r5,lr}; mov r4,r0
HOOK_SAVE  = 0x080124A0                        # FUN_080124a0 preset save entry (b.w); displaces push {r3-r5,lr}; mov r4,r0
HOOK_JR    = 0x080152BC                        # FUN_080152bc knob-state ring write (b.w); displaces push {r0,r1,r4-r6,lr}; adds r0,#1
CRC_END    = 0x0803FFFC
CRC_REGION = CRC_END - IMG_BASE                # 212988

def wslpath(p):
    d, rest = p[0], p[2:].replace("\\", "/")
    return f"/mnt/{d.lower()}{rest}"

def thumb_bl(pc, target):
    imm = target - (pc + 4)
    if imm & 1:
        raise ValueError("odd BL target")
    if not (-(1 << 24) <= imm < (1 << 24)):
        raise ValueError("BL out of range")
    S    = (imm >> 24) & 1
    I1   = (imm >> 23) & 1
    I2   = (imm >> 22) & 1
    imm10 = (imm >> 12) & 0x3FF
    imm11 = (imm >> 1) & 0x7FF
    J1 = (1 ^ I1 ^ S) & 1
    J2 = (1 ^ I2 ^ S) & 1
    hi = 0xF000 | (S << 10) | imm10
    lo = 0xD000 | (J1 << 13) | (J2 << 11) | imm11
    return bytes([hi & 0xFF, hi >> 8, lo & 0xFF, lo >> 8])

def thumb_bw(pc, target):
    """Thumb-2 B.W (encoding T4): same layout as BL but bit 14 of the low half is 0,
    so LR is left untouched (needed when hooking a function's first instruction)."""
    b = bytearray(thumb_bl(pc, target))
    lo = b[2] | (b[3] << 8)
    lo &= ~0x4000
    b[2], b[3] = lo & 0xFF, lo >> 8
    return bytes(b)

def selftest_bl():
    cases = [
        (0x080167EE, 0x080132A0, "fcf757fd"),
        (0x08019E38, 0x080132A0, "f9f732fa"),
        (0x08019D9A, 0x08013824, "f9f743fd"),
    ]
    for pc, tgt, exp in cases:
        got = thumb_bl(pc, tgt).hex()
        assert got == exp, f"BL encoder FAIL pc={pc:#x} tgt={tgt:#x} got {got} exp {exp}"
    print("  BL encoder self-test: OK")

DEBUG = "--debug" in sys.argv                   # adds the MIDI CC readout and counters

def assemble():
    cs   = os.path.join(HERE, "cave.s")
    obj  = os.path.join(HERE, "cave.o")
    binf = os.path.join(HERE, "cave.bin")
    dbg  = "-Wa,--defsym,DEBUG=1 " if DEBUG else ""
    print(f"  build: {'DEBUG' if DEBUG else 'release'}")
    cmd = (f"cd {wslpath(HERE)} && "
           f"arm-none-eabi-gcc -c -mcpu=cortex-m4 -mthumb -mfloat-abi=soft {dbg}{wslpath(cs)} -o {wslpath(obj)} && "
           f"arm-none-eabi-objcopy -O binary {wslpath(obj)} {wslpath(binf)} && "
           f"arm-none-eabi-nm {wslpath(obj)}")
    r = subprocess.run(["wsl.exe", "-d", "Ubuntu-24.04", "--", "bash", "-lc", cmd],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout); print(r.stderr); raise SystemExit("assemble failed")
    syms = {}
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[1] in ("t", "T"):
            syms[parts[2]] = int(parts[0], 16)
    blob = open(binf, "rb").read()
    print(f"  cave assembled: {len(blob)} bytes, T1=+0x{syms.get('T1',0):x} T2=+0x{syms.get('T2',0):x}")
    return blob, syms

def main():
    print("[1] BL encoder"); selftest_bl()
    print("[2] assemble cave"); cave, syms = assemble()
    t1 = CAVE_ADDR + syms["T1"] if "T1" in syms else None
    t2 = CAVE_ADDR + syms["T2"]

    print("[3] splice image")
    img = bytearray(open(STOCK_BIN, "rb").read())
    assert CAVE_OFF >= len(img), "cave overlaps image"
    img += b"\xFF" * (CAVE_OFF - len(img))        # pad to cave
    img += cave                                    # place cave
    # patch hook sites
    def patch(addr, target_sym):
        off = addr - IMG_BASE
        img[off:off+4] = thumb_bl(addr, target_sym)
    if t1 is not None:
        patch(HOOK_PLAY, t1)
    patch(HOOK_REC,  t2)
    if "DIAG" in syms:
        off = HOOK_CC - IMG_BASE
        assert img[off:off+4] == bytes.fromhex("512870b5"), "CC hook site bytes unexpected"
        img[off:off+4] = thumb_bw(HOOK_CC, CAVE_ADDR + syms["DIAG"])
    if "HOOKQ" in syms:
        off = HOOK_Q - IMG_BASE
        assert img[off:off+4] == bytes.fromhex("024b1b78"), "DSP funnel hook site bytes unexpected"
        img[off:off+4] = thumb_bw(HOOK_Q, CAVE_ADDR + syms["HOOKQ"])
    if "POLL" in syms:
        off = HOOK_POLL - IMG_BASE
        assert img[off:off+4] == bytes.fromhex("2de9f04f"), "router entry bytes unexpected"
        img[off:off+4] = thumb_bw(HOOK_POLL, CAVE_ADDR + syms["POLL"])
    if "LDHOOK" in syms:
        off = HOOK_LOAD - IMG_BASE
        assert img[off:off+4] == bytes.fromhex("38b50446"), "preset load entry bytes unexpected"
        img[off:off+4] = thumb_bw(HOOK_LOAD, CAVE_ADDR + syms["LDHOOK"])
    if "SVHOOK" in syms:
        off = HOOK_SAVE - IMG_BASE
        assert img[off:off+4] == bytes.fromhex("38b50446"), "preset save entry bytes unexpected"
        img[off:off+4] = thumb_bw(HOOK_SAVE, CAVE_ADDR + syms["SVHOOK"])
    if "JRHOOK" in syms:
        off = HOOK_JR - IMG_BASE
        assert img[off:off+4] == bytes.fromhex("73b50130"), "ring write entry bytes unexpected"
        img[off:off+4] = thumb_bw(HOOK_JR, CAVE_ADDR + syms["JRHOOK"])
    # Pad to a 256-byte boundary with erased-flash 0xFF so every .syx data
    # block is a full 256 bytes, matching the stock framing exactly. These
    # bytes lie in already-erased flash inside the CRC region, so the
    # post-flash integrity CRC is unchanged.
    if len(img) % 256:
        img += b"\xFF" * (256 - (len(img) % 256))
    open(OUT_BIN, "wb").write(img)
    print(f"  patched image: {len(img)} bytes -> {OUT_BIN}")

    # integrity CRC the pedal will report after flashing (bootloader writes it)
    region = bytes(img) + b"\xFF" * (CRC_REGION - len(img))
    crc = zlib.crc32(region) & 0xFFFFFFFF
    print(f"  post-flash integrity CRC-32 (at 0x0803FFFC) = 0x{crc:08X}")

    print("[4] rebuild .syx")
    tpl = open(STOCK_SYX, "rb").read()
    # Stamp the image length + region CRC into the START/END markers so the
    # flasher's CRC check matches our image (stock markers claim the stock CRC).
    syx = syx_encode.build_full(tpl, bytes(img), region_crc=crc)
    open(OUT_SYX, "wb").write(syx)
    back = syx_fw.decode(syx)
    print(f"  {OUT_SYX}: {len(syx)} bytes; decode round-trip ok = {back == bytes(img)}")

    print("[5] verify patched sites + cave")
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    def show(addr, n, label):
        off = addr - IMG_BASE
        print(f"  --- {label} @ 0x{addr:08X} ---")
        for ins in md.disasm(bytes(img[off:off+n]), addr):
            print(f"    0x{ins.address:08X}: {ins.bytes.hex():10s} {ins.mnemonic} {ins.op_str}")
    show(HOOK_PLAY, 4, "playback hook (expect bl T1)" if t1 else "old playback site (expect stock bl 0x08019B7C)")
    show(HOOK_REC, 4, "record hook (expect bl T2)")
    if "DIAG" in syms:
        show(HOOK_CC, 4, f"CC hook (expect b.w DIAG @ 0x{CAVE_ADDR + syms['DIAG']:08X})")
    if "HOOKQ" in syms:
        show(HOOK_Q, 4, f"DSP funnel hook (expect b.w HOOKQ @ 0x{CAVE_ADDR + syms['HOOKQ']:08X})")
    else:
        show(HOOK_Q, 4, "DSP funnel (expect stock ldr r3 / ldrb r3)")
    if "POLL" in syms:
        show(HOOK_POLL, 4, f"router entry hook (expect b.w POLL @ 0x{CAVE_ADDR + syms['POLL']:08X})")
    if "LDHOOK" in syms:
        show(HOOK_LOAD, 4, f"preset load hook (expect b.w LDHOOK @ 0x{CAVE_ADDR + syms['LDHOOK']:08X})")
        show(CAVE_ADDR + syms["LDHOOK"], 0x16, "LDHOOK cave")
    if "SVHOOK" in syms:
        show(HOOK_SAVE, 4, f"preset save hook (expect b.w SVHOOK @ 0x{CAVE_ADDR + syms['SVHOOK']:08X})")
        show(CAVE_ADDR + syms["STOCK_SAVE"], 0x0C, "STOCK_SAVE trampoline")
    if "JRHOOK" in syms:
        show(HOOK_JR, 4, f"ring write hook (expect b.w JRHOOK @ 0x{CAVE_ADDR + syms['JRHOOK']:08X})")
        show(CAVE_ADDR + syms["STOCK_JR"], 0x10, "STOCK_JR trampoline")
    if t1:
        show(t1, 0x40, "T1 cave")
    show(t2, 0x60, "T2 cave")

if __name__ == "__main__":
    main()
