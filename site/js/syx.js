/**
 * NightSky firmware .syx codec. Port of tools/syx_fw.py and tools/syx_encode.py
 * (the Python files are the reference, tools/patch/test_site.mjs holds the two
 * together byte for byte).
 *
 * A .syx is a stream of SysEx messages: F0 00 01 55 13 05 <cmd> 0C <payload> F7.
 * The payload packs 7 data bytes into 8: a byte with the high bits, then the
 * 7 low-7-bit bytes. A data message unpacks to
 *   01 <c1> <off:u32 LE> <len:u32 LE> <chk:u32 LE> <data>
 * and chk is the sum of the data as little-endian u32 words.
 * Marker messages before and after the data carry the image length and CRC.
 */

export const HEADER_LEN = 8;

export function splitSysex(raw) {
  const out = [];
  let i = 0;
  while (i < raw.length) {
    if (raw[i] !== 0xf0) { i++; continue; }
    const j = raw.indexOf(0xf7, i);
    if (j < 0) throw new Error("a SysEx message has no end byte (F7)");
    out.push(raw.subarray(i, j + 1));
    i = j + 1;
  }
  return out;
}

export function unpack7(payload) {
  const out = [];
  for (let k = 0; k < payload.length; k += 8) {
    const hi = payload[k];
    for (let t = 1; t < 8 && k + t < payload.length; t++) {
      out.push(payload[k + t] | (((hi >> (7 - t)) & 1) << 7));
    }
  }
  return Uint8Array.from(out);
}

export function pack7(data) {
  const out = [];
  for (let k = 0; k < data.length; k += 7) {
    const g = data.subarray(k, k + 7);
    let hi = 0;
    g.forEach((b, t) => { hi |= ((b >> 7) & 1) << (6 - t); });
    out.push(hi);
    g.forEach((b) => out.push(b & 0x7f));
  }
  return Uint8Array.from(out);
}

const u32 = (d, at) => (d[at] | (d[at + 1] << 8) | (d[at + 2] << 16) | (d[at + 3] << 24)) >>> 0;
const putU32 = (d, at, v) => { d[at] = v & 255; d[at + 1] = (v >>> 8) & 255; d[at + 2] = (v >>> 16) & 255; d[at + 3] = (v >>> 24) & 255; };

function payloadOf(m) {
  return m.length <= HEADER_LEN + 1 ? null : unpack7(m.subarray(HEADER_LEN, m.length - 1));
}

const isData = (m) => { const d = payloadOf(m); return d !== null && d.length > 0 && d[0] === 1; };

/** The controller image: the data blocks, concatenated in offset order. */
export function decode(raw) {
  const parts = [];
  let size = 0;
  for (const m of splitSysex(raw)) {
    const d = payloadOf(m);
    if (!d || !d.length || d[0] !== 1) continue;
    const off = u32(d, 2), len = u32(d, 6);
    if (off !== size) throw new Error(`a data block starts at ${off}, but the image has ${size} bytes`);
    parts.push(d.subarray(14, 14 + len));
    size += len;
  }
  const img = new Uint8Array(size);
  let at = 0;
  for (const p of parts) { img.set(p, at); at += p.length; }
  return img;
}

function blockChecksum(data) {
  let total = 0;
  for (let i = 0; i < data.length; i += 4) total = (total + u32(data, i)) >>> 0;
  return total;
}

function concat(chunks) {
  const out = new Uint8Array(chunks.reduce((n, c) => n + c.length, 0));
  let at = 0;
  for (const c of chunks) { out.set(c, at); at += c.length; }
  return out;
}

function rewriteMarker(m, imageLen, regionCrc) {
  const d = payloadOf(m);
  if (!d || d.length !== 14 || (d[0] !== 0 && d[0] !== 2)) return m;
  const n = Uint8Array.from(d);
  putU32(n, 6, imageLen);
  putU32(n, 10, regionCrc >>> 0);
  const padded = new Uint8Array(n.length + ((7 - (n.length % 7)) % 7));
  padded.set(n);
  return concat([m.subarray(0, HEADER_LEN), pack7(padded), Uint8Array.of(0xf7)]);
}

/** A full .syx for IMAGE, with the template's headers and its markers rewritten. */
export function buildFull(template, image, regionCrc, block = 256) {
  const msgs = splitSysex(template);
  const dataIdx = msgs.map((m, i) => (isData(m) ? i : -1)).filter((i) => i >= 0);
  const first = dataIdx[0], last = dataIdx[dataIdx.length - 1];
  const hdr = msgs[first].subarray(0, HEADER_LEN);
  const c1 = payloadOf(msgs[first])[1];
  const out = [];
  for (const m of msgs.slice(0, first)) out.push(rewriteMarker(m, image.length, regionCrc));
  for (let off = 0; off < image.length; off += block) {
    const data = image.subarray(off, off + block);
    const rec = new Uint8Array(14 + data.length + ((7 - ((14 + data.length) % 7)) % 7));
    rec[0] = 1; rec[1] = c1;
    putU32(rec, 2, off); putU32(rec, 6, data.length); putU32(rec, 10, blockChecksum(data));
    rec.set(data, 14);
    out.push(hdr, pack7(rec), Uint8Array.of(0xf7));
  }
  for (const m of msgs.slice(last + 1)) out.push(rewriteMarker(m, image.length, regionCrc));
  return concat(out);
}

let table = null;
/** zlib CRC-32 (reflected, poly 0xEDB88320). */
export function crc32(bytes) {
  if (!table) {
    table = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      table[n] = c >>> 0;
    }
  }
  let c = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) c = table[(c ^ bytes[i]) & 255] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}
