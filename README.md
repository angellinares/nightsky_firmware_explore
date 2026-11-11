# NightSky Firmware Explore

An exploration of new features for the Strymon NightSky reverb pedal, through
changes to its firmware. This is an unofficial project. Strymon does not make,
test or support it.

The first result is a mod for firmware 1.07. The step sequencer of the pedal
records nine more knobs per step: REVERB, DRY, DEPTH, INTERVAL, LOW CUT,
LENGTH, SPEED, SHIMMER and HIGH CUT. The stock SIZE/PITCH sequence works as
before. The lanes save with presets and survive a power-off.

**Patcher, manual and changelog:** the `site/` page, published with GitHub
Pages. It patches your own copy of the firmware in your browser.

## Control side only

The NightSky has two processors:

- The **controller** (an STM32 microcontroller) reads the knobs, buttons and
  MIDI. It drives the LEDs, runs the sequencer and stores the presets. It
  sends parameter values to the DSP.
- The **DSP** makes the sound. It runs the reverb algorithms.

A firmware update has a separate file for each processor:
`1305_0107_fwu.syx` for the controller and `1305_0107_fwd.syx` for the DSP.

All the mods change the controller file only. The project does not change
the DSP file, and the patcher does not read it. No audio code changes. The mod sends values
to the DSP through the same path that a knob turn uses.

## No Strymon firmware or code in this repository

This repository holds our own code and documentation only.

- It contains no Strymon firmware, in full or in part. It contains no
  decompiled Strymon code and no Strymon manual.
- The patcher carries only our own code (`tools/patch/cave.s`, compiled)
  and the branch instructions that call it. It identifies the stock file by
  its SHA-256 hash, not by stock bytes.
- You supply the stock firmware file. The Strymon Update app downloads it to
  your computer. The patcher reads that file in your browser and sends it
  nowhere.
- The notes in `docs/` name stock function addresses and data layouts. Our
  code needs these facts to work with the stock firmware.

## Repository

| Path | Content |
|---|---|
| `site/` | The patcher page: `index.html`, the JS codec and patcher, the generated patch data |
| `tools/patch/cave.s` | The mod, in ARM Thumb-2 assembly |
| `tools/patch/build_patch.py` | Builds the patched image and `.syx` from a local stock file |
| `tools/patch/gen_site.py` | Generates `site/js/nightsky-code.js` from the release build |
| `tools/patch/test_site.mjs` | Checks the JS patcher against the Python build, byte for byte |
| `tools/patch/history.json` | Release history: the source of the version and the changelog |
| `tools/syx_fw.py`, `tools/syx_encode.py` | Decode and encode the firmware `.syx` format |
| `tools/diag_read.py`, `tools/tail_read.py`, `tools/flash_read.py` | MIDI readouts for debug builds |
| `tools/ghidra/`, `tools/ghidra_analyze.ps1`, `tools/fwdb.py` | Analysis helpers |
| `docs/` | Research notes |

## Build

The build needs the stock files in `firmware-backup/v1.07/` (not in the
repository), Python 3 with `capstone`, and `arm-none-eabi-gcc` in WSL.

1. Run `python tools/patch/build_patch.py`. Add `--debug` for the MIDI
   readout.
2. Run `python tools/patch/gen_site.py` to update the patch data of the page.
3. Run `node tools/patch/test_site.mjs` to check the page against the build.

## Licence

[GNU AGPL-3.0-or-later](LICENSE).

Strymon and NightSky are trademarks of their owner. This project is not
affiliated with Strymon.
