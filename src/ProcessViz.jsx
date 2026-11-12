import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { COMP, CYCLE_HOURS, LAYERS, PHASES, SERIES, SUMMARY, phaseAt, state } from "./process.js";
import { isCut, loadKiln, makeRenderer, watch } from "./kilnModel.js";
import { markZone, tuneEnv, workshop } from "./workshop.js";

const CYCLE = 36;                         // seconds on screen for one full batch (≈ 22 h of process time)
const V = (x, y, z) => new THREE.Vector3(x, y, z);
const RET = { R: 0.85, L: 2.68, axisY: 1.39, z: 0.13 };     // half retort in the shell (drawing УП040.003-4)

// gas paths in kiln coordinates (three: x along the kiln, y up, +z = front)
const P = {
  gas: (s) => [V(s * 1.748, 1.94, -1.27), V(s * 1.25, 2.0, -1.12), V(s * 0.703, 1.997, -1.102), V(s * 0.703, 1.4, -1.102), V(s * 0.703, 0.88, -1.102), V(s * 0.63, 0.78, -1.102), V(s * 0.6, 0.9, -0.95)],
  steam: (s) => [V(s * 1.748, 1.94, -1.27), V(s * 1.25, 2.0, -1.12), V(s * 0.703, 1.997, -1.102), V(s * 0.703, 2.8, -1.102), V(s * 0.703, 3.45, -1.102), V(s * 0.75, 4.6, -1.0)],
  flue: (s) => [V(s * 0.62, 0.95, -0.9), V(s * 0.63, 1.7, -0.2), V(s * 0.95, 2.36, 0.1), V(s * 1.748, 2.42, 0.2), V(s * 2.6, 2.1, 0.4), V(s * 2.82, 1.0, 0.8), V(s * 2.95, 0.5, 1.1), V(s * 3.28, 0.55, 1.2), V(s * 3.28, 3.5, 1.2), V(s * 3.28, 7.1, 1.2)],
  air: (s) => [V(-2.55, 0.5, -2.05), V(-2.62, 0.62, -1.82), V(-2.4, 0.62, -1.72), V(s * 0.62, 0.62, -1.72), V(s * 0.62, 0.9, -1.72), V(s * 0.62, 0.9, -1.25), V(s * 0.62, 0.92, -1.0)],
  fire: (s) => [V(0, 0.45, 0.9), V(s * 0.5, 0.7, 1.1), V(s * 1.1, 0.42, 0.5), V(s * 2.2, 0.6, 0.6), V(s * 2.82, 1.0, 0.8), V(s * 2.95, 0.5, 1.1), V(s * 3.28, 0.55, 1.2), V(s * 3.28, 7.1, 1.2)],
};

/* black-body colour (Tanner Helland fit) and visible radiance ∝ Planck tail — metal starts to glow at ≈ 525 °C (Draper point) */
function blackbody(tc, out = new THREE.Color()) {
  const t = (tc + 273.15) / 100;
  const r = 255, g = t <= 66 ? 99.47 * Math.log(t) - 161.12 : 288 * Math.pow(t - 60, -0.0755), b = t <= 19 ? 0 : 138.5 * Math.log(t - 10) - 305;
  return out.setRGB(r / 255, Math.min(255, Math.max(0, g)) / 255, Math.min(255, Math.max(0, b)) / 255, THREE.SRGBColorSpace);
}
const glowOf = (tc) => { const K = tc + 273.15; return K < 790 ? 0 : Math.min(1.6, Math.pow((K - 790) / 450, 2)); };

function dot() {
  const c = document.createElement("canvas"); c.width = c.height = 64; const g = c.getContext("2d");
  const gr = g.createRadialGradient(32, 32, 0, 32, 32, 32); gr.addColorStop(0, "rgba(255,255,255,1)"); gr.addColorStop(0.35, "rgba(255,255,255,.5)"); gr.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = gr; g.fillRect(0, 0, 64, 64); const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}
/* particle stream along a path; advected with a speed taken from the model (m/s → path fraction/s) */
function flow(scene, tex, key, color, n, size, spread, blend = THREE.AdditiveBlending) {
  const curves = [-1, 1].map((s) => new THREE.CatmullRomCurve3(P[key](s), false, "centripetal"));
  const len = curves[0].getLength();
  const geo = new THREE.BufferGeometry(), pos = new Float32Array(n * 3); geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  const mat = new THREE.PointsMaterial({ color, size, map: tex, transparent: true, depthWrite: false, blending: blend, opacity: 0 });
  const pts = new THREE.Points(geo, mat); pts.frustumCulled = false; pts.renderOrder = 5; scene.add(pts);
  const seeds = Array.from({ length: n }, (_, i) => ({ s: i % 2, u: Math.random(), j: [Math.random() - 0.5, Math.random() - 0.5, Math.random() - 0.5].map((v) => v * spread) }));
  const tmp = new THREE.Vector3();
  let off = 0;
  return (dt, k, speed) => {
    mat.opacity = k; pts.visible = k > 0.02; if (!pts.visible) return;
    off = (off + (dt * speed) / len) % 1;
    seeds.forEach((sd, i) => { curves[sd.s].getPointAt((sd.u + off) % 1, tmp); pos[i * 3] = tmp.x + sd.j[0]; pos[i * 3 + 1] = tmp.y + sd.j[1]; pos[i * 3 + 2] = tmp.z + sd.j[2]; });
    geo.attributes.position.needsUpdate = true;
  };
}
function halfShell(R, L, a0, a1, seg = 40) {
  const pos = [], idx = [];
  for (let i = 0; i <= seg; i++) { const a = a0 + (a1 - a0) * i / seg; for (const z of [-L / 2, L / 2]) pos.push(R * Math.cos(a), R * Math.sin(a), z); }
  for (let i = 0; i < seg; i++) { const a = i * 2; idx.push(a, a + 2, a + 1, a + 1, a + 2, a + 3); }
  const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3)); g.setIndex(idx); g.computeVertexNormals(); return g;
}
function retort(scene, x, open) {
  const steel = new THREE.MeshStandardMaterial({ color: 0x8a8d93, metalness: 0.55, roughness: 0.5, side: THREE.DoubleSide, emissive: 0xff5a14, emissiveIntensity: 0 });
  const g = new THREE.Group(); g.position.set(x, RET.axisY, RET.z); scene.add(g);
  const add = (geo, px = 0, py = 0, pz = 0) => { const m = new THREE.Mesh(geo, steel); m.position.set(px, py, pz); m.castShadow = true; g.add(m); return m; };
  add(halfShell(RET.R, RET.L, Math.PI, 2 * Math.PI));
  add(new THREE.CircleGeometry(RET.R, 40, Math.PI, Math.PI), 0, 0, -RET.L / 2);
  if (!open) { add(halfShell(RET.R, RET.L, 0, Math.PI)); add(new THREE.CircleGeometry(RET.R, 40, 0, Math.PI), 0, 0, -RET.L / 2); }
  for (const s of [-1, 1]) add(new THREE.BoxGeometry(0.05, 0.016, RET.L), s * (RET.R + 0.022), 0, 0);
  return { g, steel };
}
/* logs in the open half retort; each log knows its layer (outer → core) so it follows that layer's temperature */
function logPile(scene, x) {
  const r = 0.058, pts = [];
  for (let y = -RET.R + r + 0.01; y < -0.02; y += 2 * r + 0.004) {
    const half = Math.sqrt(Math.max((RET.R - 0.01) ** 2 - (Math.abs(y) + r) ** 2, 0)) - r;
    const n = Math.floor((2 * half) / (2 * r + 0.006)) + 1;
    for (let i = 0; i < n; i++) for (const z of [-0.665, 0.665]) pts.push([x - ((n - 1) * (2 * r + 0.006)) / 2 + i * (2 * r + 0.006), RET.axisY + y, RET.z + z]);
  }
  const geo = new THREE.CylinderGeometry(r, r, 1.28, 10); geo.rotateX(Math.PI / 2);
  const mesh = new THREE.InstancedMesh(geo, new THREE.MeshStandardMaterial({ roughness: 0.85 }), pts.length);
  const m4 = new THREE.Matrix4();
  const layer = pts.map(([px, py]) => Math.min(LAYERS - 1, Math.floor((1 - Math.hypot(px - x, py - RET.axisY) / RET.R) * LAYERS)));
  const rnd = pts.map(() => Math.random());
  pts.forEach((p, i) => { m4.makeTranslation(...p); mesh.setMatrixAt(i, m4); mesh.setColorAt(i, new THREE.Color(0xd6cdb8)); });
  mesh.castShadow = true; scene.add(mesh);
  return { mesh, layer, rnd, n: pts.length };
}
/* wood colour from the layer state: wet → dry → torrefied → char, plus thermal glow */
const C_WET = new THREE.Color(0xcdbf9f), C_DRY = new THREE.Color(0xd9c391), C_TORR = new THREE.Color(0x6b3c1c), C_CHAR = new THREE.Color(0x18181a);
function woodColor(T, wood, water, jitter, out) {
  out.copy(C_WET).lerp(C_DRY, 1 - water);
  const deg = 1 - wood;                                       // share already decomposed
  if (T > 200) out.lerp(C_TORR, Math.min(1, deg * 2.2) * Math.min(1, (T - 200) / 80));
  out.lerp(C_CHAR, Math.max(0, Math.min(1, (deg - 0.35) / 0.5)) * (0.9 + 0.2 * jitter));
  return out;
}

/* PLC interlock on fan failure: no air → no combustion. Air dampers and the check valve close (no back-flow of hot gas
   into the air main), the firebox is blocked, the vent («свеча») opens and the pyrolysis gas goes to the flare. */
function applyFault(s) {
  if (s.mode === "cool") return { ...s, fault: true };
  return { ...s, fault: true, fanHz: 0, fanKW: 0, airDamper: 0, candleOpen: true, o2: 20.9, lambda: 0, Qcomb: 0, Qfb: 0, fire: 0,
    gas: 0, steam: Math.max(s.steam, s.gas, 0.35), ventKgH: s.fuelKgH + s.ventKgH + s.steamKgH };
}

export function ProcessViz() {
  const mountRef = useRef(null);
  const ctl = useRef({ p: 0.05, playing: true, fault: false });
  const [fault, setFault] = useState(false);
  const [p, setP] = useState(0.05);
  const [playing, setPlaying] = useState(true);
  const [ready, setReady] = useState(false);
  const [tab, setTab] = useState("charge");

  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) { ctl.current.playing = false; setPlaying(false); ctl.current.p = 0.45; setP(0.45); }
    const mount = mountRef.current;
    const renderer = makeRenderer(mount);
    const scene = new THREE.Scene(); workshop(scene, renderer);
    const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 200);
    camera.position.set(-6.8, 6.2, 10.2);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(0.2, 1.7, 0); controls.enableDamping = true; controls.minDistance = 4; controls.maxDistance = 16; controls.maxPolarAngle = 1.5; controls.minPolarAngle = 0.9;
    const w = watch(mount, renderer, camera);
    const tex = dot();
    const flows = {
      gas: flow(scene, tex, "gas", 0x5b8cff, 300, 0.13, 0.08),
      steam: flow(scene, tex, "steam", 0xeef3ff, 260, 0.2, 0.14, THREE.NormalBlending),
      flue: flow(scene, tex, "flue", 0xff6a1a, 560, 0.16, 0.22),
      air: flow(scene, tex, "air", 0x7fd6ff, 240, 0.09, 0.05),
      fire: flow(scene, tex, "fire", 0xffa040, 300, 0.15, 0.18),
    };
    // flames in the afterburning zones and in the firebox — colour from the zone temperature
    const flames = [];
    for (const s of [-1, 1]) for (let k = 0; k < 7; k++) {
      const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, color: 0xff7a22, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
      sp.position.set(s * 0.64, 0.95, -1.0 + k * 0.33); sp.userData = { base: sp.position.clone(), ph: Math.random() * 6, kind: "burner" }; scene.add(sp); flames.push(sp);
    }
    for (let k = 0; k < 4; k++) {
      const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, color: 0xffa040, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
      sp.position.set(-0.2 + k * 0.13, 0.45, 0.9); sp.userData = { base: sp.position.clone(), ph: Math.random() * 6, kind: "firebox" }; scene.add(sp); flames.push(sp);
    }
    const left = retort(scene, -1.748, true), right = retort(scene, 1.748, false);
    const pile = logPile(scene, -1.748);
    const col = new THREE.Color(), bb = new THREE.Color();
    let shellMats = [], disposed = false, raf;
    loadKiln().then((k) => {
      if (disposed) return;
      k.traverse((o) => {
        if (!o.isMesh) return;
        o.castShadow = o.receiveShadow = true;
        if (isCut(o)) o.visible = false;
        if (/^Стакан_(камера|кольцо|днище)/.test(o.name)) { o.material = o.material.clone(); o.material.emissive = new THREE.Color(0xff4a10); shellMats.push(o.material); }
      });
      scene.add(k); markZone(scene, k); tuneEnv(scene, scene); setReady(true);
    });
    const light = new THREE.PointLight(0xff7a2a, 0, 6, 1.6); light.position.set(0, 0.9, 0); scene.add(light);
    const light2 = new THREE.PointLight(0xff7a2a, 0, 6, 1.6); light2.position.set(1.2, 0.9, -0.3); scene.add(light2);

    const clock = new THREE.Clock(); let t = 0, lastUi = 0;
    const VIS = 0.12;                    // on-screen slow-down of real gas velocities so particles stay readable
    function frame() {
      raf = requestAnimationFrame(frame);
      const dt = Math.min(clock.getDelta(), 0.05);
      if (!w.isVisible()) return;
      const c = ctl.current;
      if (c.playing) c.p = (c.p + dt / CYCLE) % 1;
      t += dt;
      const s0 = state(c.p), s = c.fault ? applyFault(s0) : s0, flick = 0.85 + 0.15 * Math.sin(t * 13) * Math.sin(t * 7.1);
      const burning = s.gas > 0.02;
      // velocities from the model: pipe gas v [m/s], flue mass flow, fan speed
      flows.gas(dt, burning ? 0.25 + 0.7 * Math.min(1, s.gas * 1.3) : 0, Math.max(1.2, s.v * VIS * 3));
      flows.steam(dt, 0.85 * Math.min(1, s.steam * 1.4), Math.max(0.8, s.v * VIS * 3));
      flows.flue(dt, s.mode === "cool" ? 0 : 0.3 + 0.6 * Math.min(1, s.flue * 1.2), 0.8 + 3.5 * s.flue);
      flows.air(dt, s.fanHz / 50, 0.4 + (s.fanHz / 50) * 2.4);
      flows.fire(dt, 0.9 * s.fire, 0.8 + 1.4 * s.fire);
      blackbody(Math.max(900, s.Tz + 250), bb);
      flames.forEach((f) => {
        const k = f.userData.kind === "burner" ? Math.min(1, s.gas * 1.2) : s.fire, ph = f.userData.ph;
        f.visible = k > 0.03;
        f.material.color.copy(f.userData.kind === "burner" ? bb : col.setHex(0xffa040));
        f.position.y = f.userData.base.y + 0.25 * k * (0.6 + 0.4 * Math.sin(t * 6 + ph));
        f.scale.setScalar((0.35 + 0.55 * k) * (0.8 + 0.25 * Math.sin(t * 9 + ph)));
        f.material.opacity = 0.9 * k * flick;
      });
      const zoneHeat = s.mode === "cool" ? 0 : Math.min(1, s.Qcomb / 900);
      light.intensity = 5 * zoneHeat * flick; light2.intensity = 5 * zoneHeat * flick + 3 * s.fire;
      // steel glows only where it is hot enough (Draper point ≈ 525 °C)
      blackbody(s.Tz, bb); shellMats.forEach((m) => { m.emissive.copy(bb); m.emissiveIntensity = 0.45 * glowOf(s.Tz) * flick; });
      blackbody(s.Twall, bb); left.steel.emissive.copy(bb); right.steel.emissive.copy(bb);
      left.steel.emissiveIntensity = right.steel.emissiveIntensity = 0.5 * glowOf(s.Twall);
      for (let i = 0; i < pile.n; i++) {
        const j = pile.layer[i], T = s.layers[j];
        woodColor(T, s.lw[j], s.lwat[j], pile.rnd[i], col);
        const g = glowOf(T) * 0.6;
        if (g > 0) col.lerp(blackbody(T, bb), Math.min(0.85, g * (0.75 + 0.25 * Math.sin(t * 1.3 + pile.rnd[i] * 9))));
        pile.mesh.setColorAt(i, col);
      }
      pile.mesh.instanceColor.needsUpdate = true;
      controls.update(); renderer.render(scene, camera);
      if (t - lastUi > 0.1) { lastUi = t; setP(c.p); }
    }
    frame();
    return () => { disposed = true; cancelAnimationFrame(raf); w.dispose(); controls.dispose(); renderer.dispose(); mount.removeChild(renderer.domElement); };
  }, []);

  const s = fault ? applyFault(state(p)) : state(p), ph = phaseAt(p);
  const toggleFault = () => { const n = !fault; setFault(n); ctl.current.fault = n; };
  const chart = useMemo(() => {
    const W = 300, H = 120, Tmax = 1000, y = (T) => H - 14 - (T / Tmax) * (H - 22);
    const line = (key) => SERIES.map((q, i) => `${i ? "L" : "M"}${(q.p * W).toFixed(1)},${y(q[key]).toFixed(1)}`).join("");
    const rMax = Math.max(...SERIES.map((q) => q.rate));
    const area = `M0,${H - 14}` + SERIES.map((q) => `L${(q.p * W).toFixed(1)},${(H - 14 - (q.rate / rMax) * 26).toFixed(1)}`).join("") + `L${W},${H - 14}Z`;
    const ticks = []; for (let h = 0; h <= CYCLE_HOURS; h += 6) ticks.push({ x: (h / CYCLE_HOURS) * W, h });
    return { W, H, y, wall: line("Twall"), core: line("Tcore"), zone: line("Tz"), area, ticks };
  }, []);
  const seek = (v) => { ctl.current.p = v; setP(v); };
  const toggle = () => { const n = !playing; setPlaying(n); ctl.current.playing = n; };
  const f0 = (x) => Math.round(x).toLocaleString("ru-RU");
  const f1 = (x) => x.toLocaleString("ru-RU", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const hh = (h) => `${String(Math.floor(h)).padStart(2, "0")}:${String(Math.floor((h % 1) * 60)).padStart(2, "0")}`;
  const cool = s.mode === "cool";
  const TABS = [["charge", "Закладка"], ["kin", "Кинетика"], ["heat", "Горение"], ["gas", "Газ и тяга"]];

  return (
    <div className="pv">
      <div className="stage pv-stage" data-hide>
        <div className="stage-canvas" ref={mountRef} role="img" aria-label={`Печь в разрезе, стадия «${ph.name}», стенка реторты ${Math.round(s.Twall)} °C, центр закладки ${Math.round(s.Tcore)} °C`} />
        {!ready && <div className="stage-loading">Загружаем печь…</div>}
        <div className="pv-phase"><span className="live" />{ph.name}<em>{ph.range}</em><span className="pv-clock">{hh(s.hours)} <small>из {f0(CYCLE_HOURS)} ч</small></span></div>
        <div className="pv-front" aria-label="Температура слоёв закладки от стенки к центру">
          <span className="pv-front-k">Стенка → центр</span>
          <div className="pv-front-bar">
            {s.layers.map((T, j) => <i key={j} style={{ background: `hsl(${Math.max(0, 48 - T / 14)}, ${T > 120 ? 90 : 25}%, ${s.lw[j] < 0.4 ? 12 + Math.min(40, T / 18) : 70 - Math.min(35, T / 14)}%)` }} title={`${Math.round(T)} °C`} />)}
          </div>
          <span className="pv-front-v">{f0(s.Twall)}° → {f0(s.Tcore)}°</span>
        </div>
        {fault && <div className="pv-alarm" role="alert"><strong>Авария: вентилятор остановлен</strong>Заслонки воздуха и обратный клапан закрыты, топка заблокирована, свеча открыта — газ уходит на сброс, обратного потока в воздуховод нет.</div>}
        <ul className="pv-legend">
          <li><i style={{ background: "#ff6a1a" }} />Дымовые газы</li>
          <li><i style={{ background: "#5b8cff" }} />Пиролизный газ → дожиг</li>
          <li><i style={{ background: "#eef3ff" }} />Пар / сброс на свечу</li>
          <li><i style={{ background: "#7fd6ff" }} />Воздух</li>
        </ul>
      </div>
      <div className="pv-side">
        <div className="pv-tabs" role="tablist" aria-label="Параметры процесса">
          {TABS.map(([id, label]) => <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? "on" : ""} onClick={() => setTab(id)}>{label}</button>)}
        </div>
        <div className="pv-block" role="tabpanel">
          {tab === "charge" && <>
            <span className="pv-label">Закладка · 2 реторты по {f0(SUMMARY.dry / 2)} кг сухой берёзы</span>
            <div className="kv"><span>Стенка реторты / центр</span><strong className="hot">{f0(s.Twall)} / {f0(s.Tcore)} °C</strong></div>
            <div className="kv"><span>Влажность закладки</span><strong>{f1(s.moisture)} %</strong></div>
            <div className="kv"><span>Масса от исходной</span><strong>{f0(s.mass * 100)} %</strong></div>
            <div className="kv"><span>Связанный углерод C<sub>fix</sub></span><strong>{s.cfix > 25 ? `${f0(s.cfix)} %` : "—"}</strong></div>
            <div className="kv"><span>Уголь в ретортах</span><strong>{f0(s.charKg)} кг</strong></div>
          </>}
          {tab === "kin" && <>
            <span className="pv-label pv-formula">Разложение: dm/dt = −A·e<sup>−E/RT</sup>·m</span>
            {COMP.map((c, i) => (
              <div className="comp" key={c.id}>
                <div className="comp-h"><span>{c.name}</span><small>E = {f0(c.E / 1000)} кДж/моль</small><strong>{f0(s.comp[i] * 100)} %</strong></div>
                <div className="comp-bar"><i style={{ width: `${s.comp[i] * 100}%` }} /></div>
              </div>
            ))}
            <div className="kv"><span>Скорость выхода летучих</span><strong>{f0(s.dmdt)} кг/ч</strong></div>
          </>}
          {tab === "heat" && <>
            <span className="pv-label">Зона дожига под стаканами</span>
            <div className="kv"><span>Температура зоны</span><strong className="hot">{f0(s.Tz)} °C</strong></div>
            <div className="kv"><span>Мощность горения</span><strong>{cool ? "—" : `${f0(s.Qcomb)} кВт`}</strong></div>
            <div className="kv"><span>— из них растопочная топка</span><strong>{f0(s.Qfb)} кВт</strong></div>
            <div className="kv"><span>Тепло в каждую реторту</span><strong>{f0(Math.abs(s.qRetort))} кВт</strong></div>
            <div className="kv"><span>Избыток воздуха λ / O₂</span><strong>{cool ? "—" : `${f1(s.lambda)} / ${f1(s.o2)} %`}</strong></div>
          </>}
          {tab === "gas" && <>
            <span className="pv-label">Газодинамика и автоматика</span>
            <div className="kv"><span>Давление в стакане</span><strong>+{f0(s.dp)} Па</strong></div>
            <div className="kv"><span>Скорость газа в ТП200</span><strong>{f1(s.v)} м/с</strong></div>
            <div className="kv"><span>Свеча · сброс</span><strong className={s.candleOpen ? "on" : ""}>{s.candleOpen ? "открыта" : s.ventKgH > 5 ? `${f0(s.ventKgH)} кг/ч` : "закрыта"}</strong></div>
            <div className="kv"><span>Тяга трубы H = 7,2 м</span><strong>{f0(s.draft)} Па</strong></div>
            <div className="kv"><span>Вентилятор (ЧРП)</span><strong>{f0(s.fanHz)} Гц · {f1(s.fanKW)} кВт</strong></div>
            <div className="kv"><span>Заслонка воздуха / шибер</span><strong>{s.airDamper} / {s.chimneyDamper} %</strong></div>
            <div className="kv"><span>Обратный клапан</span><strong className={fault ? "" : "on"}>{fault || s.fanHz === 0 ? "закрыт" : "открыт"}</strong></div>
            <button className={fault ? "pv-fault on" : "pv-fault"} onClick={toggleFault} aria-pressed={fault}>{fault ? "Вернуть вентилятор в работу" : "Смоделировать отказ вентилятора"}</button>
          </>}
        </div>
        <svg className="pv-chart" viewBox={`0 0 ${chart.W} ${chart.H}`} preserveAspectRatio="none" aria-label="Температуры за цикл: зона дожига, стенка реторты, центр закладки">
          {PHASES.map((q) => <rect key={q.id} x={q.from * chart.W} y="0" width={(q.to - q.from) * chart.W} height={chart.H} className={q.id === ph.id ? "band on" : "band"} />)}
          <path d={chart.area} className="rate" />
          <path d={chart.zone} className="curve zone" />
          <path d={chart.wall} className="curve" />
          <path d={chart.core} className="curve core" />
          {chart.ticks.map((k) => <text key={k.h} x={k.x + 2} y={chart.H - 3} className="tick">{k.h} ч</text>)}
          <line x1={p * chart.W} x2={p * chart.W} y1="0" y2={chart.H} className="now" />
          <circle cx={p * chart.W} cy={chart.y(s.Twall)} r="3.2" className="mark" />
        </svg>
        <div className="pv-key"><span><i className="k-zone" />зона</span><span><i className="k-wall" />стенка</span><span><i className="k-core" />центр</span><span><i className="k-rate" />выход газа</span></div>
        <div className="pv-note"><code>{ph.formula}</code><p>{ph.note}</p></div>
      </div>
      <div className="pv-time">
        <button className="play" onClick={toggle} aria-label={playing ? "Пауза" : "Запустить"}>{playing ? "❚❚" : "▶"}</button>
        <div className="pv-track">
          <div className="pv-chips">{PHASES.map((q) => <button key={q.id} style={{ flexGrow: q.to - q.from }} className={q.id === ph.id ? "on" : ""} onClick={() => seek(q.from + 0.002)}>{q.name}</button>)}</div>
          <input type="range" min="0" max="0.999" step="0.001" value={p} onChange={(e) => seek(+e.target.value)} aria-label="Положение в цикле" />
        </div>
      </div>
    </div>
  );
}
