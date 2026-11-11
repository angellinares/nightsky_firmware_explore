# NightSky firmware notes

Target: Strymon NightSky, firmware 1.07. These notes record what the mod
needs to know about the stock controller firmware. All addresses are for
1.07. The notes contain no stock code.

## Update files

- An update is a stream of SysEx messages:
  `F0 00 01 55 13 05 <cmd> 0C <payload> F7`. Command `0x43` carries the
  controller image (`fwu`). Command `0x42` carries the DSP image (`fwd`).
- The payload packs 7 data bytes into 8. The first byte of each group holds
  the high bits.
- A data message unpacks to
  `01 <c1> <off:u32> <len:u32> <chk:u32> <data>`. The value `chk` is the sum
  of the data as little-endian u32 words.
- A marker message before and after the data holds the image length and the
  integrity CRC.
- `tools/syx_fw.py` decodes a file. `tools/syx_encode.py` encodes one. A
  stock file decodes and encodes back byte for byte.

## Integrity check

- The controller image loads at `0x0800C000`. The bootloader occupies
  `0x08000000`..`0x08007FFF`.
- The integrity value is a standard CRC-32 (`zlib.crc32`). It covers
  `0x0800C000`..`0x0803FFFB`, with `0xFF` past the end of the image. The
  bootloader writes it at `0x0803FFFC`.
- The pedal reports it on SysEx command `0x31`. A build is correct when
  that value matches the value from `build_patch.py`.
- The firmware has no signature. The CRC protects against damage, not
  against changes.

## Hooks

The mod is in `tools/patch/cave.s`. It sits at `0x08023500`, past the end
of the stock image, in erased flash. Five 4-byte branch instructions call
it.

| Address | Stock function | Purpose |
|---|---|---|
| `0x080132A2` | parameter send to the DSP | record knob values, play the lanes on each step |
| `0x08015C48` | button and knob router, every main-loop pass | RAM init, steps 3+6 chord, ON LED |
| `0x080121C4` | preset load (`p = 0x7F`: knob mode) | restore the lanes of the preset |
| `0x080124A0` | preset save | save the lanes in the preset slot |
| `0x080152BC` | knob-state ring write | save the knob-mode lanes |

Each hook re-runs the stock instructions that its branch replaces.

## RAM

The lanes use `0x2000EC00`..`0x2000ECCB`. This area is above the stock
heap and below the stack. A pedal test measured more than 4 KB that the
stack never used, between this area and the stack.

| Offset | Content |
|---|---|
| `0x00` | 9 lanes x 8 steps, u16 each. `0xFFFF` = no record |
| `0x90` | 9 base values, u16 |
| `0xA4` | init marker `0x5AA5` |
| `0xA6` | bit per lane: the lane has records |
| `0xA8` | bit per lane: the base value is set |
| `0xAA` | live recording armed (`0xA5`) |

## External flash

The controller stores its data in an external SPI NOR flash of 2 MB.

| Range | Content |
|---|---|
| `0x040000`..`0x0D64FF` | 301 preset slots of `0x800` bytes. Stock uses `0x4FC` bytes of each |
| `0x0F0000`..`0x12FFFF` | stock knob-state ring: 1024 pages of 256 bytes |
| `0x130000`..`0x16FFFF` | lane ring of the mod (blank on stock pedals) |
| `0x1F0000` | stock global settings |

- Stock functions: read `0x08012628`, sector write with erase `0x0801281C`,
  page program `0x08012718`, erase `0x08012794`.
- Preset `p` is at `0x40000 + p * 0x800`. The display shows `p + 1`. The
  checksum of the preset is at slot `+0x4F8`.
- The knob-state ring: each write goes to the next page. Byte `0xFF` of the
  newest page is `0xA1`. Bytes `0xFB`..`0xFE` hold a write counter. A step
  toggle calls `0x08015360` (mark changed). A main-loop timer then writes.

## Lane records

A record is `0xC0` bytes:

| Offset | Content |
|---|---|
| `0x00` | magic `0x4C4E` |
| `0x02` | version `1` |
| `0x04` | tag: the preset checksum, or the ring write counter |
| `0x08` | RAM block `0x00`..`0xA9` |
| `0xB2` | CRC-16/CCITT of `0x00`..`0xB1` |

- Preset save: the record goes to slot `+0x700`, after the stock save. The
  tag is the checksum that the stock save wrote.
- Preset load: the mod copies the record only if the magic, the version,
  the CRC and the tag all match. Else it clears the lanes.
- Knob mode: the record goes to `0x130000 + page * 0x100`, after each stock
  ring write. At power-up, the mod reads the page of the newest stock page.
  The tag must equal the stock write counter.

## Known limits

- The Strymon app writes presets with SysEx command `0x61`. That path does
  not call the preset save, so the old record stays. Its tag no longer
  matches, so it does not load.
- The factory preset reset erases `0x40000`..`0x8FFFF` only. Records in
  higher slots stay, with a tag that no longer matches.
