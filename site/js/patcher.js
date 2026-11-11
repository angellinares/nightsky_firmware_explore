/**
 * Patch a stock NightSky 1.07 controller update (.syx) with the knob-lane mod.
 * Mirrors tools/patch/build_patch.py. Works on any JS runtime with WebCrypto
 * (browsers, node 18+).
 */
import { decode, buildFull, crc32 } from "./syx.js";
import { PATCH } from "./nightsky-code.js";

const IMG_PAGE = 256;

export async function sha256(bytes) {
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  return Array.from(digest, (b) => b.toString(16).padStart(2, "0")).join("");
}

function fromBase64(s) {
  const bin = atob(s);
  return Uint8Array.from(bin, (c) => c.charCodeAt(0));
}

const hex = (s) => Uint8Array.from(s.match(/../g).map((h) => parseInt(h, 16)));
const h8 = (v) => (v >>> 0).toString(16).toUpperCase().padStart(8, "0");

/**
 * Patch RAW (the bytes of the stock update file). Returns { syx, crc, steps }
 * or throws an Error that says why the file was refused.
 */
export async function patch(raw) {
  const steps = [];
  const fileHash = await sha256(raw);
  if (fileHash === PATCH.outSyxSha256) {
    throw new Error(`This file is already patched with version ${PATCH.version}. Upload the stock file.`);
  }
  if (fileHash !== PATCH.stockSyxSha256) {
    let image;
    try { image = decode(raw); } catch { image = null; }
    if (image && (await sha256(image)) === PATCH.stockImageSha256) {
      steps.push("The file holds the stock 1.07 image in a different message layout.");
    } else {
      throw new Error(`This is not the stock ${PATCH.stockName} controller update (1305_0107_fwu.syx). `
        + "Only that file is supported. Do not use the DSP file (fwd).");
    }
  } else {
    steps.push(`Stock file recognised: ${PATCH.stockName}, controller update.`);
  }

  const stock = decode(raw);
  if ((await sha256(stock)) !== PATCH.stockImageSha256) throw new Error("The decoded image does not match stock 1.07.");

  const caveOff = PATCH.caveAddr - PATCH.imageBase;
  const cave = fromBase64(PATCH.cave);
  let size = caveOff + cave.length;
  size += (IMG_PAGE - (size % IMG_PAGE)) % IMG_PAGE;
  const img = new Uint8Array(size).fill(0xff);
  img.set(stock);
  img.set(cave, caveOff);
  for (const e of PATCH.edits) img.set(hex(e.bytes), e.addr - PATCH.imageBase);
  steps.push(`Added ${cave.length} bytes of new code at 0x${h8(PATCH.caveAddr)} and ${PATCH.edits.length} branch instructions.`);

  const region = new Uint8Array(PATCH.crcEnd - PATCH.imageBase).fill(0xff);
  region.set(img);
  const crc = crc32(region);
  steps.push(`Integrity CRC-32: ${h8(crc)}.`);

  const syx = buildFull(raw, img, crc);
  if ((await sha256(img)) !== PATCH.outImageSha256 || (await sha256(syx)) !== PATCH.outSyxSha256) {
    throw new Error("The result does not match the reference build. Nothing was written. Please report this.");
  }
  steps.push("The result matches the reference build byte for byte.");
  return { syx, crc: h8(crc), steps };
}
