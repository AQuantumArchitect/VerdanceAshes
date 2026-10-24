// The planet: Verdance's Ashes as a globe, the hub's way into a field.
//
// Fields the company can go to are painted on at their true shape from each map's own picture
// (art/fields/<mapId>.jpg); everything else is uncharted ash. Roads run between doors; a road that
// leads past the walked world is drawn into the dark and ends in "?". A filled door is one the
// company's ledger says it holds. Only the company's record is drawn (hub_state.world), never truth.
//
// Plain canvas, no library: an orthographic sphere sampled per pixel from an equirectangular
// texture, redrawn only while it moves.

// Where each field sits on the planet (degrees), and its turn (quarter turns clockwise). Laid out
// so every road leaves its field from the side facing the far field and crosses open ash: the
// chain runs Greenest -> Koom -> Tabula -> Bastion -> Simmers -> Eye -> home, with home's shortcut
// east to Tabula. Greenest Fields sits turned a quarter anticlockwise: the start road leaves both
// it and the Rock Jungle from their north-west corners, so one of the two must turn to face the
// other. (Searched over every turn and placement; see the globe layout note in the project docs.)
const PLACE = {
  the_rock_jungle:  { lon: 0,     lat: 0 },
  greenest_fields:  { lon: -12,   lat: 27.1, rot: 3 },
  koom_valley:      { lon: 20.7,  lat: 32.8 },
  tabula:           { lon: 32.2,  lat: 10.9 },
  ancient_bastion:  { lon: 28.1,  lat: -8.8 },
  all_that_simmers: { lon: 57.7,  lat: -26.6 },
  eye_of_horus:     { lon: 30,    lat: -30.1 },
};
const SIZE = 26;           // degrees across a field's long side
const TW = 2048, TH = 1024;
const RAD = Math.PI / 180;

const G = {
  canvas: null, host: null, ctx: null,
  yaw: 0, pitch: 0.1, toYaw: 0, toPitch: 0.1,
  images: {}, loading: null,
  texKey: "", tex: null,
  opts: null, raf: 0, drag: null,
};

function css(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

// ---- texture ----------------------------------------------------------------------------------
function hash(x, y) { const s = Math.sin(x * 127.1 + y * 311.7) * 43758.5453; return s - Math.floor(s); }
function noise(x, y) {
  const xi = Math.floor(x), yi = Math.floor(y), xf = x - xi, yf = y - yi;
  const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
  const a = hash(xi, yi), b = hash(xi + 1, yi), c = hash(xi, yi + 1), d = hash(xi + 1, yi + 1);
  return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
}
let ground = null;
function groundCanvas() {
  if (ground) return ground;
  const w = 512, h = 256, small = document.createElement("canvas");
  small.width = w; small.height = h;
  const sc = small.getContext("2d"), img = sc.createImageData(w, h);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    // sample at the texel's point on the sphere: no seam at the date line, no stretch at the poles
    const lon = (x / w - 0.5) * Math.PI * 2, lat = (0.5 - y / h) * Math.PI;
    const vx = Math.cos(lat) * Math.sin(lon), vy = Math.sin(lat), vz = Math.cos(lat) * Math.cos(lon);
    let n = 0, amp = 1, f = 4.5;
    for (let o = 0; o < 5; o++) {
      n += amp * 0.5 * (noise(vx * f + 11, vy * f + 3) + noise(vz * f + 29, vy * f + 17));
      amp *= 0.5; f *= 2;
    }
    n /= 1.94;
    const ash = 18 + n * 70, green = n > 0.55 ? (n - 0.55) * 170 : 0;
    const i = (y * w + x) * 4;
    img.data[i] = ash * 0.9; img.data[i + 1] = ash + green * 0.8; img.data[i + 2] = ash * 0.84 + green * 0.3; img.data[i + 3] = 255;
  }
  sc.putImageData(img, 0, 0);
  ground = document.createElement("canvas");
  ground.width = TW; ground.height = TH;
  ground.getContext("2d").drawImage(small, 0, 0, TW, TH);
  return ground;
}
// A field may sit turned on the planet (PLACE.rot, quarter turns clockwise) so that each road's
// two doors face each other across the gap; its picture and its doors turn with it.
function turned(m) { return ((PLACE[m] && PLACE[m].rot) || 0) % 4; }
function fieldRect(m) {
  const p = PLACE[m], im = G.images[m];
  let iw = im ? im.naturalWidth : 1, ih = im ? im.naturalHeight : 1;
  if (turned(m) % 2) [iw, ih] = [ih, iw];
  const big = Math.max(iw, ih);
  const wDeg = SIZE * iw / big, hDeg = SIZE * ih / big;
  const lonSpan = wDeg / Math.cos(p.lat * RAD);
  return { lon0: p.lon - lonSpan / 2, lat0: p.lat + hDeg / 2, lonSpan, hDeg };
}
// A point on the map (x east, z south, 0..1) to the same point on the turned field.
function turnPoint(m, x, z) {
  for (let k = 0; k < turned(m); k++) [x, z] = [1 - z, x];
  return [x, z];
}
const texX = lon => (lon + 180) / 360 * TW;
const texY = lat => (90 - lat) / 180 * TH;
function buildTexture(visible) {
  const key = visible.slice().sort().join(",");
  if (key === G.texKey && G.tex) return;
  const c = document.createElement("canvas"); c.width = TW; c.height = TH;
  const x = c.getContext("2d");
  x.drawImage(groundCanvas(), 0, 0);
  for (const m of visible) {
    if (!PLACE[m] || !G.images[m]) continue;
    const r = fieldRect(m);
    const px = texX(r.lon0), py = texY(r.lat0), w = r.lonSpan / 360 * TW, h = r.hDeg / 180 * TH;
    const k = turned(m);
    x.save();
    x.translate(px + w / 2, py + h / 2);
    x.rotate(k * Math.PI / 2);
    if (k % 2) x.drawImage(G.images[m], -h / 2, -w / 2, h, w);
    else x.drawImage(G.images[m], -w / 2, -h / 2, w, h);
    x.restore();
    x.strokeStyle = "rgba(238,246,238,.7)"; x.lineWidth = 2; x.strokeRect(px, py, w, h);
  }
  G.tex = x.getImageData(0, 0, TW, TH).data;
  G.texKey = key;
}

// ---- projection -------------------------------------------------------------------------------
// local (lon 0 faces the viewer at yaw 0) -> view: Rx(pitch) * Ry(yaw)
function toLocal(lon, lat) {
  const cl = Math.cos(lat * RAD);
  return [cl * Math.sin(lon * RAD), Math.sin(lat * RAD), cl * Math.cos(lon * RAD)];
}
function toView([x, y, z]) {
  const cy = Math.cos(G.yaw), sy = Math.sin(G.yaw), cp = Math.cos(G.pitch), sp = Math.sin(G.pitch);
  const x1 = x * cy + z * sy, z1 = -x * sy + z * cy;
  return [x1, y * cp - z1 * sp, y * sp + z1 * cp];
}
function fromView([x, y, z]) {
  const cy = Math.cos(G.yaw), sy = Math.sin(G.yaw), cp = Math.cos(G.pitch), sp = Math.sin(G.pitch);
  const y1 = y * cp + z * sp, z1 = -y * sp + z * cp;
  return [x * cy - z1 * sy, y1, x * sy + z1 * cy];
}
function geom() {
  const w = G.canvas.clientWidth, h = G.canvas.clientHeight;
  return { w, h, cx: w / 2, cy: h / 2, R: Math.min(w, h) * 0.47 };
}
function project(lon, lat, lift = 0) {
  const { cx, cy, R } = geom();
  const v = toView(toLocal(lon, lat)), r = R * (1 + lift);
  return { x: cx + v[0] * r, y: cy - v[1] * r, front: v[2] > 0.02 };
}

// ---- drawing ----------------------------------------------------------------------------------
function drawSphere(ctx, g) {
  const scale = Math.min(1.5, window.devicePixelRatio || 1);
  const size = Math.ceil(g.R * 2 * scale) + 2;
  const img = ctx.createImageData(size, size), d = img.data, tex = G.tex;
  const L = [-0.45, 0.5, 0.74];
  for (let j = 0; j < size; j++) {
    const ny = -((j + 0.5) / scale - g.R) / g.R;
    for (let i = 0; i < size; i++) {
      const nx = ((i + 0.5) / scale - g.R) / g.R, rr = nx * nx + ny * ny;
      if (rr > 1) continue;
      const nz = Math.sqrt(1 - rr);
      const p = fromView([nx, ny, nz]);
      const lon = Math.atan2(p[0], p[2]), lat = Math.asin(Math.max(-1, Math.min(1, p[1])));
      const tx = Math.min(TW - 1, Math.floor((lon / (2 * Math.PI) + 0.5) * TW));
      const ty = Math.min(TH - 1, Math.floor((0.5 - lat / Math.PI) * TH));
      const t = (ty * TW + tx) * 4, o = (j * size + i) * 4;
      const lit = 0.42 + 0.85 * Math.max(0, nx * L[0] + ny * L[1] + nz * L[2]);
      d[o] = tex[t] * lit; d[o + 1] = tex[t + 1] * lit; d[o + 2] = tex[t + 2] * lit;
      d[o + 3] = rr > 0.985 ? 255 * (1 - rr) / 0.015 : 255;
    }
  }
  const off = document.createElement("canvas"); off.width = size; off.height = size;
  off.getContext("2d").putImageData(img, 0, 0);
  ctx.drawImage(off, g.cx - g.R, g.cy - g.R, g.R * 2, g.R * 2);
}
function drawHalo(ctx, g) {
  const grad = ctx.createRadialGradient(g.cx, g.cy, g.R * 0.96, g.cx, g.cy, g.R * 1.12);
  grad.addColorStop(0, "rgba(61,143,85,.45)");
  grad.addColorStop(1, "rgba(61,143,85,0)");
  ctx.fillStyle = grad;
  ctx.beginPath(); ctx.arc(g.cx, g.cy, g.R * 1.12, 0, Math.PI * 2); ctx.fill();
}
function doorLonLat(end) {
  const r = fieldRect(end.mapId), [x, z] = turnPoint(end.mapId, end.x, end.z);
  return [r.lon0 + x * r.lonSpan, r.lat0 - z * r.hDeg];
}
function slerpPath(a, b, upto) {
  const va = toLocal(a[0], a[1]), vb = toLocal(b[0], b[1]);
  const dot = Math.max(-1, Math.min(1, va[0] * vb[0] + va[1] * vb[1] + va[2] * vb[2]));
  const om = Math.acos(dot), so = Math.sin(om) || 1, out = [], n = 48;
  for (let i = 0; i <= n; i++) {
    const t = i / n * upto;
    const k1 = Math.sin((1 - t) * om) / so, k2 = Math.sin(t * om) / so;
    const v = [va[0] * k1 + vb[0] * k2, va[1] * k1 + vb[1] * k2, va[2] * k1 + vb[2] * k2];
    const lat = Math.asin(Math.max(-1, Math.min(1, v[1]))) / RAD, lon = Math.atan2(v[0], v[2]) / RAD;
    out.push(project(lon, lat, 0.004 + Math.sin(Math.PI * i / n) * 0.05 * upto));
  }
  return out;
}
function drawRoads(ctx, visible) {
  const amber = css("--warn", "#e0a060"), muted = css("--muted", "#7d9584");
  for (const road of (G.opts.roads || [])) {
    const aOn = visible.includes(road.a.mapId), bOn = visible.includes(road.b.mapId);
    if (!aOn && !bOn) continue;
    const [from, to] = aOn ? [road.a, road.b] : [road.b, road.a];
    const known = aOn && bOn;
    const pts = slerpPath(doorLonLat(from), PLACE[to.mapId] ? doorLonLat(to) : doorLonLat(from), known ? 1 : 0.6);
    ctx.save();
    ctx.strokeStyle = amber; ctx.globalAlpha = known ? 0.95 : 0.7; ctx.lineWidth = 2; ctx.setLineDash([6, 5]);
    ctx.beginPath();
    let pen = false;
    for (const p of pts) {
      if (!p.front) { pen = false; continue; }
      if (pen) ctx.lineTo(p.x, p.y); else { ctx.moveTo(p.x, p.y); pen = true; }
    }
    ctx.stroke(); ctx.restore();
    if (!known) {
      const tip = pts[pts.length - 1];
      if (tip.front) {
        ctx.fillStyle = muted; ctx.font = "600 15px system-ui, sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
        ctx.fillText("?", tip.x, tip.y);
      }
    }
    for (const end of [road.a, road.b]) {
      if (!visible.includes(end.mapId)) continue;
      const [lon, lat] = doorLonLat(end), p = project(lon, lat, 0.004);
      if (!p.front) continue;
      ctx.fillStyle = css("--bg", "#040907"); ctx.strokeStyle = amber; ctx.lineWidth = 2;
      ctx.fillRect(p.x - 4.5, p.y - 4.5, 9, 9); ctx.strokeRect(p.x - 4.5, p.y - 4.5, 9, 9);
      if (end.held) { ctx.fillStyle = amber; ctx.fillRect(p.x - 4.5, p.y - 4.5, 9, 9); }
    }
  }
}
function drawLabels(ctx, visible) {
  const gold = css("--gold", "#d4c49a"), ink = css("--ink", "#eef6ee"), good = css("--good", "#7dff8a");
  for (const m of visible) {
    if (!PLACE[m] || !G.images[m]) continue;
    // The name sits just inside the field's top edge, so neighbours a road-gap apart never collide.
    const r = fieldRect(m), p = project(PLACE[m].lon, r.lat0 - 1.0, 0.01);
    if (!p.front) continue;
    const focused = m === G.opts.focus;
    ctx.font = `${focused ? 700 : 600} ${focused ? 14 : 12}px system-ui, sans-serif`;
    ctx.textAlign = "center"; ctx.textBaseline = "top";
    ctx.lineWidth = 4; ctx.strokeStyle = "rgba(4,9,7,.85)"; ctx.strokeText(G.opts.names[m] || m, p.x, p.y);
    ctx.fillStyle = focused ? ink : gold; ctx.fillText(G.opts.names[m] || m, p.x, p.y);
    const water = (G.opts.water || {})[m];
    if (water && focused) {     // the next sortie's water there: dry bed, shallows, amphibious
      const q = project(PLACE[m].lon, r.lat0 - r.hDeg + 1.0, 0.01);
      if (q.front) {
        ctx.font = "600 11px system-ui, sans-serif"; ctx.textBaseline = "bottom";
        ctx.lineWidth = 3; ctx.strokeText(`≈ ${water}`, q.x, q.y);
        ctx.fillStyle = css("--steam", "#7ec8ff"); ctx.fillText(`≈ ${water}`, q.x, q.y);
      }
    }
    if (focused) {     // trace the field's edge
      ctx.save(); ctx.strokeStyle = good; ctx.lineWidth = 2; ctx.beginPath();
      const edge = [];
      for (let i = 0; i <= 12; i++) edge.push([r.lon0 + r.lonSpan * i / 12, r.lat0]);
      for (let i = 0; i <= 12; i++) edge.push([r.lon0 + r.lonSpan, r.lat0 - r.hDeg * i / 12]);
      for (let i = 0; i <= 12; i++) edge.push([r.lon0 + r.lonSpan * (1 - i / 12), r.lat0 - r.hDeg]);
      for (let i = 0; i <= 12; i++) edge.push([r.lon0, r.lat0 - r.hDeg * (1 - i / 12)]);
      edge.forEach(([lo, la], i) => { const q = project(lo, la, 0.002); if (i) ctx.lineTo(q.x, q.y); else ctx.moveTo(q.x, q.y); });
      ctx.stroke(); ctx.restore();
    }
  }
}
function draw() {
  if (!G.tex || !G.opts) return;      // pictures still loading
  const ctx = G.ctx, g = geom(), dpr = window.devicePixelRatio || 1;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, g.w, g.h);
  drawHalo(ctx, g);
  drawSphere(ctx, g);
  drawRoads(ctx, G.opts.visible);
  drawLabels(ctx, G.opts.visible);
}
function tick() {
  G.raf = 0;
  const k = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 1 : 0.18;
  G.yaw += (G.toYaw - G.yaw) * k; G.pitch += (G.toPitch - G.pitch) * k;
  draw();
  if (Math.abs(G.toYaw - G.yaw) > 0.001 || Math.abs(G.toPitch - G.pitch) > 0.001) G.raf = requestAnimationFrame(tick);
}
function kick() { if (!G.raf) G.raf = requestAnimationFrame(tick); }
// Turn to the focused field, leaning toward the middle of the walked world so its neighbours
// stay on the near side of the planet.
function faceField(m) {
  if (!PLACE[m]) return;
  const seen = ((G.opts && G.opts.visible) || []).filter(v => PLACE[v]);
  const mid = k => seen.reduce((s, v) => s + PLACE[v][k], 0) / (seen.length || 1);
  const lon = seen.length > 1 ? 0.6 * PLACE[m].lon + 0.4 * mid("lon") : PLACE[m].lon;
  const lat = seen.length > 1 ? 0.6 * PLACE[m].lat + 0.4 * mid("lat") : PLACE[m].lat;
  let yaw = -lon * RAD;
  while (yaw - G.yaw > Math.PI) yaw -= 2 * Math.PI;
  while (G.yaw - yaw > Math.PI) yaw += 2 * Math.PI;
  G.toYaw = yaw; G.toPitch = lat * RAD;
}

// ---- input ------------------------------------------------------------------------------------
function fieldAt(ev) {
  const rect = G.canvas.getBoundingClientRect(), g = geom();
  const nx = (ev.clientX - rect.left - g.cx) / g.R, ny = -(ev.clientY - rect.top - g.cy) / g.R, rr = nx * nx + ny * ny;
  if (rr > 1) return null;
  const p = fromView([nx, ny, Math.sqrt(1 - rr)]);
  const lon = Math.atan2(p[0], p[2]) / RAD, lat = Math.asin(p[1]) / RAD;
  for (const m of G.opts.visible) {
    if (!PLACE[m] || !G.images[m]) continue;
    const r = fieldRect(m);
    const dLon = ((lon - r.lon0) % 360 + 360) % 360;
    if (dLon <= r.lonSpan && lat <= r.lat0 && lat >= r.lat0 - r.hDeg) return m;
  }
  return null;
}
function wire() {
  const c = G.canvas;
  c.addEventListener("pointerdown", ev => { G.drag = { x: ev.clientX, y: ev.clientY, moved: 0 }; c.setPointerCapture(ev.pointerId); });
  c.addEventListener("pointermove", ev => {
    if (!G.drag) { c.style.cursor = fieldAt(ev) ? "pointer" : "grab"; return; }
    const dx = ev.clientX - G.drag.x, dy = ev.clientY - G.drag.y;
    G.drag.x = ev.clientX; G.drag.y = ev.clientY; G.drag.moved += Math.abs(dx) + Math.abs(dy);
    G.toYaw += dx * 0.008; G.toPitch = Math.max(-1.2, Math.min(1.2, G.toPitch + dy * 0.008));
    G.yaw = G.toYaw; G.pitch = G.toPitch; kick();
  });
  c.addEventListener("pointerup", ev => {
    const moved = G.drag ? G.drag.moved : 99;
    G.drag = null;
    if (moved < 6) { const m = fieldAt(ev); if (m && G.opts.onPick) G.opts.onPick(m); }
  });
  new ResizeObserver(() => { size(); draw(); }).observe(G.host);
}
function size() {
  const dpr = window.devicePixelRatio || 1, w = G.host.clientWidth, h = Math.max(260, Math.min(440, Math.round(w * 0.55)));
  G.canvas.style.height = h + "px";
  G.canvas.width = Math.round(w * dpr); G.canvas.height = Math.round(h * dpr);
}
function loadImages() {
  if (G.loading) return G.loading;
  G.loading = Promise.all(Object.keys(PLACE).map(m => new Promise(res => {
    const im = new Image();
    im.onload = () => { G.images[m] = im; res(); };
    im.onerror = () => res();
    im.src = `art/fields/${m}.jpg`;
  })));
  return G.loading;
}

// opts: { visible: [mapId], focus: mapId, roads: hub world roads, names: {mapId: name},
//         water: {mapId: assault word}, onPick(mapId) }
export function renderGlobe(host, opts) {
  if (!host) return;
  const first = !G.canvas || G.host !== host;
  if (first) {
    host.innerHTML = `<canvas class="globe-canvas" role="img" aria-label="The planet. Drag to turn it; click a lit field to open it."></canvas>`;
    G.host = host; G.canvas = host.querySelector("canvas"); G.ctx = G.canvas.getContext("2d");
    wire(); size();
  }
  const focusChanged = !G.opts || G.opts.focus !== opts.focus;
  G.opts = opts;
  loadImages().then(() => {
    buildTexture(opts.visible);
    if (focusChanged || first) faceField(opts.focus);
    if (first) { G.yaw = G.toYaw; G.pitch = G.toPitch; }
    kick();
  });
}
