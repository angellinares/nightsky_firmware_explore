# Plan: save the knob lanes with presets

Status: v15 (CRC `3F52644F`) is tested on the pedal. Preset save, preset
load and the knob-mode power-up restore work. v16 (CRC `2AB4D028`) is the
release build of the same code without the debug parts.

The debug parts build only with `build_patch.py --debug`: the MIDI CC
readout (CC 120..127), the counters and the stack paint. The debug build is
byte-exact v15. The tools `diag_read.py`, `tail_read.py` and
`flash_read.py` need a debug build.

## Knob mode across power-off (v15)

Stock keeps the knob-mode sequence through a power-off. A test on the pedal
showed this. The lanes now do the same.

- Stock writes a 256-byte knob-state record to a ring of 1024 pages at
  `0xF0000`..`0x12FFFF` (`FUN_080152bc`). A step toggle calls
  `FUN_08015360`, and a main-loop timer then writes the record.
- The hook on `FUN_080152bc` writes a lane record to
  `0x130000 + page * 0x100`, after the stock write. The record holds the
  stock ring counter at `+0x04`.
- A lane record or a lane clear calls `FUN_08015360`. The stock timer then
  writes both rings.
- At power-up, the lane init reads the lane page of the newest stock page.
  It copies the lanes only if magic, version, CRC and counter all match.
- A scan on the pedal showed `0x130000`..`0x16FFFF` all `0xFF` before v15.

## Goal

The knob lanes survive a power cycle. Each preset keeps its own lanes, the
same way it keeps its SIZE/PITCH sequence.

## Decisions (agreed 2026-11-11)

1. A preset save also saves the lanes, base levels and flags.
2. A preset recall replaces the lanes. A preset with no saved lanes clears
   them. Unsaved lane edits are lost on recall, the same as stock knob edits.
3. The lanes save only with the stock preset save. No automatic save.

## Where the presets live (research result)

The earlier finding "the DSP stores the presets" is wrong. The controller
stores them in an external SPI NOR flash.

- Preset `p` (0..300) sits at `0x40000 + p * 0x800`. Each slot is 2 KB.
- A preset uses `0x4FC` bytes of the slot. Word `+0x000` holds the magic
  `0x7E81`. Word `+0x4F8` holds a checksum (`FUN_08018c0c`).
- Bytes `0x4FC`..`0x7FF` of each slot are unused: 772 bytes per preset.
- `FUN_0801281c(addr, len, buf)` writes the external flash. It reads the
  4 KB sector, patches the bytes, erases the sector (command `0x20`) and
  programs it again in 256-byte pages. So it keeps the other bytes of the
  sector.
- `FUN_08012628(addr, len, buf)` reads the external flash.
- Other stock writes use `0x1F0000` and `0x1FFFF8`..`0x1FFFFF`. They do not
  touch the preset slots.

Stock functions for the hooks:

| Function | Role | Callers |
|---|---|---|
| `FUN_080124a0(p)` | Save the edit buffer to preset `p` | FAVORITE save confirm (`0x08016F2E`), event `0x3D` (`0x08016EC8`) |
| `FUN_080121c4(p)` | Load preset `p`. `p = 0x7F` is a special case | preset buttons, MIDI recall, 5 more |
| `FUN_08019104(p, buf)` | Read and check one preset | `FUN_080121c4` and others |

## Design

The lanes go into the unused tail of each preset slot, at
`0x40000 + p * 0x800 + 0x700`. No internal flash write, no journal and no
compaction. All 300 presets can hold lanes.

Tail record, 0xC0 bytes:

| Offset | Size | Content |
|---|---|---|
| `0x00` | 2 | magic `0x4C4E` ("LN") |
| `0x02` | 2 | format version |
| `0x04` | 4 | checksum of the preset saved with it (`+0x4F8`) |
| `0x08` | 0xAA | RAM block `0x2000EC00`..`0x2000ECAA`: lanes, bases, flags |
| `0xB2` | 2 | CRC-16 of bytes `0x00`..`0xB1` |
| `0xB4` | 12 | `0xFF` |

- Save hook on `FUN_080124a0`: the stock save runs first. Then the hook
  writes the tail record with `FUN_0801281c`. A save then erases the same
  4 KB sector two times. Stock erases it one time.
- Load hook on `FUN_080121c4`, `p` not `0x7F`: the stock load runs first.
  Then the hook reads the tail record into a stack buffer. The hook copies
  the record into the lane RAM only if the magic, the CRC and the preset
  checksum all match. Otherwise the hook clears the lanes and the bases.
- The checksum match ties the lanes to one saved version of the preset.
  If the editor restores a preset, its checksum changes. The old lanes then
  do not load.

## Open items

1. Find the event that calls `FUN_080124a0` at `0x08016EC8`. It can be a
   MIDI or editor save. The lanes save there too.
2. Done. Power-up does not recall a preset. The pedal starts in knob mode
   and the lanes start empty. One preset button press calls `FUN_080121c4`
   one time, and preset 12 on the display is `p = 11`. A return to knob mode
   calls `FUN_080121c4(0x7F)`. Decide what the lanes do then.
3. Done. Presets 0, 1, 2 and 15: bytes `0x4FC`..`0x4FF` are `81 7E 00 00`.
   Bytes `0x500`..`0x7FF` are `0xFF`.
4. Find the factory reset. It can leave old tail records. The checksum
   check rejects them.

## Build and test steps

Each step is one flash. Each step adds a MIDI readout.

1. Read-only test: a CC command reads a slot tail and sends it back over
   SysEx. Read the tails of some presets. No write in this build.
2. Save: the save hook writes the tail record. Save a preset. Read its tail
   back with the step 1 command.
3. Load: the load hook reads the tail record. To test, save a preset and
   power-cycle the pedal. Then recall the preset. Then read the lanes with
   `diag_read.py`.
4. Clean-up: remove the debug commands that are not needed.

## Risks

- A wrong address in a write could damage another preset or the global
  settings. The hook computes the address from `p` only after it checks
  `p < 0x12D`. The address always ends in `0x700` inside the slot.
- A power loss during a save can damage the 4 KB sector. Stock has the same
  risk for every save.
- The Strymon app backs up 0x4FC bytes per preset, as far as we know. The
  lanes are not in its backups.
