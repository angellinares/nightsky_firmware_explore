// Check the web patcher against the Python reference build, byte for byte.
//   node tools/patch/test_site.mjs
// Needs firmware-backup/v1.07/1305_0107_fwu.syx (stock, not in the repo) and
// the reference output out/fwu_v107_revstep.syx from build_patch.py (release).
import { readFileSync } from "node:fs";
import { patch } from "../../site/js/patcher.js";
import { decode, buildFull, splitSysex } from "../../site/js/syx.js";

const stock = new Uint8Array(readFileSync("firmware-backup/v1.07/1305_0107_fwu.syx"));
const ref = new Uint8Array(readFileSync("out/fwu_v107_revstep.syx"));
const same = (a, b) => a.length === b.length && a.every((v, i) => v === b[i]);
let fail = 0;
const check = (name, ok) => { console.log(`${ok ? "ok  " : "FAIL"} ${name}`); if (!ok) fail++; };

const img = decode(stock);
check(`decode: ${splitSysex(stock).length} messages, ${img.length} bytes`, img.length === 95432);
const out = await patch(stock);
check(`patch output equals the Python build (${ref.length} bytes, CRC ${out.crc})`, same(out.syx, ref));
for (const bad of [ref, decode(stock), new Uint8Array(10)]) {
  let refused = false;
  try { await patch(bad); } catch { refused = true; }
  check(`refuses a non-stock input of ${bad.length} bytes`, refused);
}
process.exit(fail ? 1 : 0);
