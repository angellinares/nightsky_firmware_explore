/**
 * Top view of the NightSky as a line drawing, laid out after the front-panel
 * drawings in the NightSky user manual (pages 4 and 19). Line work only, no
 * shading. Only the LEDs that matter for live recording are drawn lit.
 * Colours come from CSS classes: .stroke .paper .muted-t (line work),
 * .led-red .led-amber .acc .acc-stroke (accents).
 *
 * drawPedal(svg, state) with state:
 *   onLed:   "red" | "acc"     ON LED colour (red = stock sequence mode)
 *   favBlink: bool             FAVORITE LED blinks red: the sequencer runs
 *   current: 0..7              step that plays now (red)
 *   active:  [bool x 8]        steps that are on (amber)
 *   press:   [step indexes]    steps the player presses (dashed ring)
 *   knob:    knob name | null  knob the player turns (ring and arrow)
 */
const NS = "http://www.w3.org/2000/svg";
function el(tag, attrs, parent, text) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text !== undefined) e.textContent = text;
  parent.appendChild(e);
  return e;
}

// Upper panel, in the coordinates of the manual's drawing (x 12..1170, y 15..360).
const SECTION_LINES = [
  [12, 15, 1170, 15], [12, 360, 1170, 360], [12, 15, 12, 360], [1170, 15, 1170, 360],
  [12, 198, 1033, 198], [545, 15, 545, 198], [1033, 15, 1033, 360], [378, 198, 378, 360],
];
const SECTION_TABS = [["MOD", 22, 38], ["DECAY", 555, 38], ["MIX", 1078, 38], ["TONE", 22, 222], ["VOICE", 388, 222]];
const KNOBS = [                       // [name, cx, cy, label y]
  ["SPEED", 78, 92, 176], ["DEPTH", 300, 92, 176], ["LENGTH", 642, 100, 176], ["SIZE/PITCH", 858, 100, 176],
  ["REVERB", 1107, 92, 176], ["LOW CUT", 78, 274, 352], ["HIGH CUT", 297, 274, 352],
  ["INTERVAL", 478, 284, 352], ["SHIMMER", 763, 276, 352], ["DRY", 1107, 268, 352],
];
const KNOB_R = (name) => (name === "INTERVAL" ? 30 : 40);   // INTERVAL is the small knob
// LED groups: [title, title x, title y, led x, led ys, labels, label side, button x, button y]
const GROUPS = [
  ["TARGET", 195, 36, 214, [57, 92, 128], ["verb", "pitch", "filter"], "l", 195, 176],
  ["SHAPE", 435, 36, 410, [57, 92, 128], [], "l", 434, 176],
  ["", 0, 0, 457, [57, 92, 128], ["", "rand", "env"], "r", null, null],
  ["TEXTURE", 745, 36, 718, [57, 92, 128], ["sparse", "dense", "diffuse"], "r", 745, 176],
  ["QUANTIZE", 960, 36, 928, [57, 92, 128], ["smooth", "half step", "scale"], "r", 958, 176],
  ["FILTER", 195, 230, 218, [255, 291], ["regen", "low pass"], "l", 195, 336],
  ["SHIMMER", 641, 230, 665, [255, 291], ["input", "regen"], "l", 641, 336],
  ["GLIMMER", 870, 230, 852, [255, 291], ["high", "low"], "r", 870, 336],
  ["DRIVE", 978, 230, 958, [255, 291], ["pre", "post"], "r", 976, 336],
];
const INTERVALS = [["-2nd", "+2nd", 246], ["-4th", "+4th", 273], ["-5th", "+5th", 300], ["-8va", "+8va", 327]];

// Lower half, measured from a photo of the pedal, in the same units.
const STEP_X = (i) => 290 + i * 85.7;
const STEP_Y = 412;
const FOOT = [                        // [name, x, upper label, lower label]
  ["ON", 111, "sequence step", "hold (morph)"],
  ["FAVORITE", 583, "sequence tap", ""],
  ["INFINITE", 1090, "", "hold (sequence)"],
];

function wave(g, x, y, kind) {        // the small SHAPE icons
  const d = {
    tri: `M ${x} ${y + 6} l 8 -10 l 8 10 l 8 -10`,
    sq: `M ${x} ${y + 6} v -10 h 10 v 10 h 10 v -10`,
    saw: `M ${x} ${y + 6} l 10 -10 v 10 l 10 -10 v 10`,
    rsaw: `M ${x} ${y - 4} v 10 l 10 -10 v 10 l 10 -10`,
  }[kind];
  el("path", { d, class: "stroke", "stroke-width": 1.6 }, g);
}

export function drawPedal(svg, state) {
  svg.setAttribute("viewBox", "0 0 1182 706");
  const g = el("g", {}, svg);
  el("rect", { x: 2, y: 2, width: 1178, height: 702, rx: 26, class: "paper" }, g);
  el("rect", { x: 2, y: 2, width: 1178, height: 702, rx: 26, class: "stroke", "stroke-width": 2.5 }, g);

  for (const [x1, y1, x2, y2] of SECTION_LINES) el("line", { x1, y1, x2, y2, class: "stroke", "stroke-width": 2 }, g);
  for (const [name, x, y] of SECTION_TABS) el("text", { x, y, class: "tab" }, g, name);

  for (const [title, tx, ty, lx, ys, labels, side, bx, by] of GROUPS) {
    if (title) el("text", { x: tx, y: ty, "text-anchor": "middle", class: "grp" }, g, title);
    ys.forEach((y, k) => {
      el("circle", { cx: lx, cy: y, r: 8, class: "stroke", "stroke-width": 1.6 }, g);
      const t = labels[k];
      if (t) el("text", { x: side === "l" ? lx - 16 : lx + 16, y: y + 6, "text-anchor": side === "l" ? "end" : "start", class: "led" }, g, t);
    });
    if (bx !== null) el("rect", { x: bx - 16, y: by - 16, width: 32, height: 32, rx: 4, class: "stroke", "stroke-width": 1.8 }, g);
  }
  wave(g, 364, 57, "tri"); wave(g, 364, 92, "sq"); wave(g, 364, 128, "saw");
  wave(g, 474, 57, "rsaw");
  for (const [l, r, y] of INTERVALS) {
    el("text", { x: 438, y, "text-anchor": "end", class: "led" }, g, l);
    el("text", { x: 520, y, "text-anchor": "start", class: "led" }, g, r);
  }

  for (const [name, cx, cy, ly] of KNOBS) {
    const marked = state.knob === name, kr = KNOB_R(name);
    el("circle", { cx, cy, r: kr, class: marked ? "acc-stroke" : "stroke", "stroke-width": marked ? 5 : 2 }, g);
    el("line", { x1: cx, y1: cy - kr * 0.3, x2: cx, y2: cy - kr * 0.8, class: "stroke", "stroke-width": 4, "stroke-linecap": "round" }, g);
    el("text", { x: cx, y: ly, "text-anchor": "middle", class: "knob" }, g, name);
    if (marked) {                     // clockwise turn arrow, outside the knob
      const r = kr + 14, a0 = -150, a1 = -40, p = (a) => [cx + r * Math.cos(a * Math.PI / 180), cy + r * Math.sin(a * Math.PI / 180)];
      const [x0, y0] = p(a0), [x1, y1] = p(a1);
      el("path", { d: `M ${x0} ${y0} A ${r} ${r} 0 0 1 ${x1} ${y1}`, class: "acc-stroke", "stroke-width": 5, "stroke-linecap": "round" }, g);
      const t = (a1 + 90) * Math.PI / 180;           // tangent direction at the end
      const head = (s) => `M ${x1} ${y1} l ${-16 * Math.cos(t + s)} ${-16 * Math.sin(t + s)}`;
      el("path", { d: head(0.5) + " " + head(-0.5), class: "acc-stroke", "stroke-width": 5, "stroke-linecap": "round" }, g);
    }
  }

  // the preset buttons: the 8 sequencer steps, lit keys with the number above
  for (let i = 0; i < 8; i++) {
    const x = STEP_X(i);
    const cls = i === state.current ? "led-red" : state.active[i] ? "led-amber" : "paper";
    el("text", { x, y: 384, "text-anchor": "middle", class: "led" }, g, String(i + 1));
    if (state.press.includes(i)) {
      el("circle", { cx: x, cy: STEP_Y, r: 32, class: "acc-stroke", "stroke-width": 4, "stroke-dasharray": "7 6" }, g);
    }
    el("circle", { cx: x, cy: STEP_Y, r: 20, class: cls }, g);
    el("circle", { cx: x, cy: STEP_Y, r: 20, class: "stroke", "stroke-width": 2 }, g);
  }

  // footswitches: label, LED, upper label, switch, lower label
  for (const [name, x, up, down] of FOOT) {
    const led = name === "ON" ? (state.onLed === "acc" ? "acc" : "led-red")
      : name === "FAVORITE" && state.favBlink ? "led-red blink" : "paper";
    el("text", { x, y: 472, "text-anchor": "middle", class: "knob" }, g, name);
    el("circle", { cx: x, cy: 494, r: 9, class: led }, g);
    el("circle", { cx: x, cy: 494, r: 9, class: "stroke", "stroke-width": 1.8 }, g);
    if (up) el("text", { x, y: 530, "text-anchor": "middle", class: "led" }, g, up);
    el("circle", { cx: x, cy: 604, r: 48, class: "stroke", "stroke-width": 2.5 }, g);
    el("circle", { cx: x, cy: 604, r: 33, class: "stroke", "stroke-width": 1.8 }, g);
    if (down) el("text", { x, y: 682, "text-anchor": "middle", class: "led" }, g, down);
  }
  return g;
}

/** Fill the figure: before the gesture, and after it. */
export function drawLiveRecordingFigure(before, after) {
  const active = [true, true, true, true, true, true, false, true];
  drawPedal(before, { onLed: "red", favBlink: true, current: 3, active, press: [2, 5], knob: null });
  drawPedal(after, { onLed: "acc", favBlink: true, current: 4, active, press: [], knob: "LENGTH" });
}
