import { patch } from "./patcher.js";
import { PATCH } from "./nightsky-code.js";
import { drawLiveRecordingFigure } from "./fig-pedal.js";

const $ = (id) => document.getElementById(id);
const NS = "http://www.w3.org/2000/svg";
function el(tag, attrs, parent, text) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text !== undefined) e.textContent = text;
  parent.appendChild(e);
  return e;
}

/* ---- version and changelog ---- */
$("ver").textContent = PATCH.version;
$("build").textContent = PATCH.build;
for (const r of PATCH.history) {
  const div = document.createElement("div");
  div.className = "release";
  div.innerHTML = `<h3>${r.version}</h3><div class="meta">${r.date} · build ${r.build} · for ${PATCH.stockName}</div>`;
  const ul = document.createElement("ul");
  for (const c of r.changes) { const li = document.createElement("li"); li.textContent = c; ul.appendChild(li); }
  div.appendChild(ul);
  $("releases").appendChild(div);
}

/* ---- figure 1: the pedal before and after arming live recording ---- */
drawLiveRecordingFigure($("pedal-before"), $("pedal-after"));

/* ---- figure 2: example lanes ---- */
{
  const g = $("lanes");
  const lanes = [
    ["LENGTH", [null, 205, null, 56, null, 190, null, 68], 122],
    ["SHIMMER", [null, null, 125, null, 126, null, null, null], 40],
    ["INTERVAL", [null, null, null, 7, null, null, null, null], 90],
  ];
  const x0 = 100, w = 64, rowH = 50, top = 22, max = 255;
  for (let s = 0; s < 8; s++) el("text", { x: x0 + s * w + w / 2, y: 14, "text-anchor": "middle", class: "small" }, g, `step ${s + 1}`);
  lanes.forEach(([name, vals, base], r) => {
    const y = top + r * rowH, h = rowH - 12;
    el("text", { x: 0, y: y + h / 2 + 4 }, g, name);
    el("rect", { x: x0, y, width: 8 * w, height: h, class: "soft" }, g);
    const by = y + h - (base / max) * h;
    el("line", { x1: x0, y1: by, x2: x0 + 8 * w, y2: by, class: "stroke", "stroke-dasharray": "4 4", "stroke-width": 1 }, g);
    vals.forEach((v, s) => {
      if (v === null) return;
      const bh = Math.max(2, (v / max) * h);
      el("rect", { x: x0 + s * w + 10, y: y + h - bh, width: w - 20, height: bh, rx: 2, class: "acc" }, g);
    });
    for (let s = 1; s < 8; s++) el("line", { x1: x0 + s * w, y1: y, x2: x0 + s * w, y2: y + h, class: "line" }, g);
  });
}

/* ---- figure 3: paired rings ---- */
{
  const g = $("ring");
  const rows = [["stock state", "soft", "stroke", 140], ["lanes", "acc-soft", "acc-stroke", 166]];
  for (const [label, fill, edge, y] of rows) {
    el("text", { x: 20, y: y + 15, class: "small" }, g, label);
    for (let i = 0; i < 16; i++) {
      const x = 110 + i * 31, newest = i === 9;
      el("rect", { x, y, width: 27, height: 20, class: newest ? (fill === "soft" ? "ink" : "acc") : fill }, g);
      el("rect", { x, y, width: 27, height: 20, class: edge, "stroke-width": 1 }, g);
    }
  }
  el("text", { x: 110 + 9 * 31 + 13, y: 136, "text-anchor": "middle", class: "small" }, g, "newest");
}

/* ---- patcher ---- */
const log = $("log"), dl = $("dl"), drop = $("drop");
function line(text, bad = false) {
  const li = document.createElement("li");
  if (bad) li.className = "bad";
  li.textContent = text;
  log.appendChild(li);
}
async function run(file) {
  log.textContent = "";
  dl.hidden = true;
  if (dl.href) URL.revokeObjectURL(dl.href);
  try {
    const raw = new Uint8Array(await file.arrayBuffer());
    const out = await patch(raw);
    out.steps.forEach((s) => line(s));
    line(`Patch ${PATCH.version} ready. Expected CRC on the pedal after flashing: ${out.crc}.`);
    dl.href = URL.createObjectURL(new Blob([out.syx], { type: "application/octet-stream" }));
    dl.hidden = false;
  } catch (e) {
    line(e.message ?? String(e), true);
  }
}
$("file").addEventListener("change", (e) => e.target.files[0] && run(e.target.files[0]));
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => {
  e.preventDefault();
  drop.classList.remove("over");
  if (e.dataTransfer.files[0]) run(e.dataTransfer.files[0]);
});
