import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";

/* Production hall around the kiln (sections 01 and 02): white sandwich-panel walls, steel columns,
   dark roof trusses with high-bay lamps, polished concrete floor, yellow safety details.
   Everything is procedural — no extra downloads. Units: metres, floor at FY. */
export const HALL = { W: 48, D: 36, H: 12 };
const FY = -0.21;

function tex(w, h, draw, rx = 1, ry = 1) {
  const c = document.createElement("canvas"); c.width = w; c.height = h;
  draw(c.getContext("2d"), w, h);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace; t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(rx, ry); t.anisotropy = 8;
  return t;
}
const rnd = (() => { let s = 7; return () => ((s = (s * 16807) % 2147483647) / 2147483647); })();

/* instanced boxes: beams(list of [a, b, thickness]) */
function beams(list, mat) {
  const geo = new THREE.BoxGeometry(1, 1, 1);
  const im = new THREE.InstancedMesh(geo, mat, list.length);
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), up = new THREE.Vector3(0, 1, 0);
  list.forEach(([a, b, t, t2], i) => {
    const d = b.clone().sub(a), len = d.length();
    q.setFromUnitVectors(up, d.normalize());
    m.compose(a.clone().add(b).multiplyScalar(0.5), q, new THREE.Vector3(t, len, t2 ?? t));
    im.setMatrixAt(i, m);
  });
  im.instanceMatrix.needsUpdate = true;
  return im;
}

function sign(text, w = 2.2, h = 1.1) {
  const t = tex(512, 256, (g, W, H) => {
    g.fillStyle = "#f2c11c"; g.fillRect(0, 0, W, H);
    g.strokeStyle = "#1b1b1b"; g.lineWidth = 10; g.strokeRect(14, 14, W - 28, H - 28);
    g.fillStyle = "#151515"; g.font = "800 150px Manrope, Arial, sans-serif"; g.textAlign = "center"; g.textBaseline = "middle";
    g.fillText(text, W / 2, H / 2 + 8);
  });
  return new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshStandardMaterial({ map: t, roughness: 0.6 }));
}

/* image-based light strength per material (scene.environmentIntensity only exists from r163) */
export function tuneEnv(root, scene) {
  const k = scene.userData.envIntensity ?? 1;
  root.traverse((o) => { const ms = o.material ? (Array.isArray(o.material) ? o.material : [o.material]) : []; ms.forEach((m) => { if ("envMapIntensity" in m) m.envMapIntensity = k; }); });
}

export function workshop(scene, renderer) {
  const { W, D, H } = HALL, g = new THREE.Group(); g.name = "Цех";
  const bg = 0xd5d9dd;
  scene.background = new THREE.Color(bg);
  scene.fog = new THREE.Fog(bg, 26, 70);

  /* soft image-based light so steel and the floor get believable reflections */
  const pm = new THREE.PMREMGenerator(renderer);
  scene.environment = pm.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.userData.envIntensity = 0.4;            // applied per material (works on three r162 / WebGL 1 too)
  renderer.toneMappingExposure = 1.0;
  pm.dispose();

  scene.add(new THREE.HemisphereLight(0xffffff, 0x7d848c, 0.95));
  const key = new THREE.DirectionalLight(0xfff6ea, 2.4);
  key.position.set(-6, 16, 8); key.castShadow = true; key.shadow.mapSize.set(2048, 2048); key.shadow.bias = -0.0004; key.shadow.normalBias = 0.02;
  Object.assign(key.shadow.camera, { left: -11, right: 11, top: 11, bottom: -11, near: 1, far: 50 });
  scene.add(key);
  const fill = new THREE.DirectionalLight(0xdfe8ff, 0.7); fill.position.set(10, 8, -10); scene.add(fill);

  /* polished concrete: mottled grey, saw-cut joints every 6 m */
  const floorMap = tex(1024, 1024, (c, S) => {
    c.fillStyle = "#a8acaf"; c.fillRect(0, 0, S, S);
    for (let i = 0; i < 260; i++) {
      const x = rnd() * S, y = rnd() * S, r = 20 + rnd() * 140, l = rnd() > 0.5;
      const gr = c.createRadialGradient(x, y, 0, x, y, r);
      gr.addColorStop(0, l ? "rgba(255,255,255,.07)" : "rgba(90,95,100,.06)"); gr.addColorStop(1, "rgba(0,0,0,0)");
      c.fillStyle = gr; c.fillRect(x - r, y - r, 2 * r, 2 * r);
    }
    c.strokeStyle = "rgba(70,74,80,.45)"; c.lineWidth = 2;
    for (const p of [0, S / 2]) { c.beginPath(); c.moveTo(p + 1, 0); c.lineTo(p + 1, S); c.moveTo(0, p + 1); c.lineTo(S, p + 1); c.stroke(); }
  }, W / 12, D / 12);
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(W, D), new THREE.MeshStandardMaterial({ map: floorMap, roughness: 0.22, metalness: 0.05 }));
  floor.rotation.x = -Math.PI / 2; floor.position.y = FY; floor.receiveShadow = true; g.add(floor);

  /* lamp glow pools on the floor (fake reflections of the high-bay lights) */
  const pool = tex(128, 128, (c, S) => {
    const gr = c.createRadialGradient(S / 2, S / 2, 0, S / 2, S / 2, S / 2);
    gr.addColorStop(0, "rgba(255,255,255,.55)"); gr.addColorStop(0.35, "rgba(255,255,255,.14)"); gr.addColorStop(1, "rgba(255,255,255,0)");
    c.fillStyle = gr; c.fillRect(0, 0, S, S);
  });
  const poolMat = new THREE.MeshBasicMaterial({ map: pool, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, opacity: 0.22 });

  /* sandwich panel walls: 1 m seams, dark girt band at 4.6 m, slightly darker towards the roof */
  const wallMap = (len) => tex(256, 1024, (c, w, h) => {
    const gr = c.createLinearGradient(0, 0, 0, h); gr.addColorStop(0, "#b9bdc2"); gr.addColorStop(0.5, "#d6d9dc"); gr.addColorStop(1, "#dfe1e3");
    c.fillStyle = gr; c.fillRect(0, 0, w, h);
    const px = h / H;
    c.fillStyle = "rgba(120,126,134,.35)";
    for (let m = 1; m < H; m++) c.fillRect(0, h - m * px, w, 2);
    c.fillStyle = "#5b6067"; c.fillRect(0, h - 4.6 * px, w, 0.14 * px);
    c.fillStyle = "#6a7078"; c.fillRect(0, h - 0.18 * px, w, 0.18 * px);   // plinth
    c.fillStyle = "rgba(120,126,134,.18)"; c.fillRect(0, 0, 2, h);
  }, len / 6, 1);
  const walls = [
    [W, [0, H / 2 + FY, -D / 2], 0], [W, [0, H / 2 + FY, D / 2], Math.PI],
    [D, [-W / 2, H / 2 + FY, 0], Math.PI / 2], [D, [W / 2, H / 2 + FY, 0], -Math.PI / 2],
  ];
  for (const [len, p, ry] of walls) {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(len, H), new THREE.MeshStandardMaterial({ map: wallMap(len), roughness: 0.75 }));
    m.position.set(...p); m.rotation.y = ry; g.add(m);
  }

  /* roof deck: dark corrugated sheet */
  const roofMap = tex(64, 64, (c, s) => {
    c.fillStyle = "#4a4f56"; c.fillRect(0, 0, s, s);
    c.fillStyle = "#5c626a"; c.fillRect(0, 0, s, s / 3);
    c.fillStyle = "#383c42"; c.fillRect(0, (2 * s) / 3, s, s / 3);
  }, 1, D / 0.6);
  const roof = new THREE.Mesh(new THREE.PlaneGeometry(W, D), new THREE.MeshStandardMaterial({ map: roofMap, roughness: 0.6, metalness: 0.3 }));
  roof.rotation.x = Math.PI / 2; roof.position.y = H + FY; g.add(roof);

  /* steel: columns on the wall grid, roof trusses every 6 m, purlins, wall X-bracing */
  const V = (x, y, z) => new THREE.Vector3(x, y + FY, z);
  const steel = new THREE.MeshStandardMaterial({ color: 0x3b4047, roughness: 0.5, metalness: 0.55 });
  const list = [];
  const xs = []; for (let x = -W / 2; x <= W / 2 + 0.01; x += 6) xs.push(x);
  const zs = []; for (let z = -D / 2; z <= D / 2 + 0.01; z += 6) zs.push(z);
  const inset = 0.3;
  for (const x of xs) {
    list.push([V(x, 0, -D / 2 + inset), V(x, H, -D / 2 + inset), 0.42], [V(x, 0, D / 2 - inset), V(x, H, D / 2 - inset), 0.42]);
    // truss across the hall
    const top = H - 0.25, bot = H - 1.9;
    list.push([V(x, top, -D / 2), V(x, top, D / 2), 0.22], [V(x, bot, -D / 2), V(x, bot, D / 2), 0.18]);
    for (let z = -D / 2, k = 0; z < D / 2 - 0.01; z += 1.5, k++) {
      list.push([V(x, bot, z), V(x, top, z), 0.08]);
      list.push(k % 2 ? [V(x, bot, z), V(x, top, z + 1.5), 0.07] : [V(x, top, z), V(x, bot, z + 1.5), 0.07]);
    }
  }
  for (const z of zs) {
    list.push([V(-W / 2 + inset, 0, z), V(-W / 2 + inset, H, z), 0.42], [V(W / 2 - inset, 0, z), V(W / 2 - inset, H, z), 0.42]);
  }
  for (let z = -D / 2 + 1.5; z < D / 2; z += 3) list.push([V(-W / 2, H - 0.12, z), V(W / 2, H - 0.12, z), 0.12]);   // purlins
  list.push([V(-W / 2, H - 1.9, 0), V(W / 2, H - 1.9, 0), 0.16]);                                                 // ridge tie
  // X-bracing in two back-wall bays and one side bay
  for (const x0 of [-18, 12]) list.push([V(x0, 0.2, -D / 2 + 0.25), V(x0 + 6, 4.4, -D / 2 + 0.25), 0.07], [V(x0 + 6, 0.2, -D / 2 + 0.25), V(x0, 4.4, -D / 2 + 0.25), 0.07]);
  list.push([V(W / 2 - 0.25, 0.2, -6), V(W / 2 - 0.25, 4.4, 0), 0.07], [V(W / 2 - 0.25, 0.2, 0), V(W / 2 - 0.25, 4.4, -6), 0.07]);
  // free-standing columns of the inner grid (kept clear of the kiln)
  const inner = [[-15, -7], [15, -7], [-15, 9], [15, 9]];
  for (const [x, z] of inner) list.push([V(x, 0, z), V(x, H - 1.9, z), 0.5]);
  g.add(beams(list, steel));

  const mm = new THREE.Matrix4();
  /* high-bay lamps on a 6 m grid with glow pools below */
  const lampXs = [], lampZs = [];
  for (let x = -W / 2 + 3; x < W / 2; x += 6) lampXs.push(x);
  for (let z = -D / 2 + 3; z < D / 2; z += 6) lampZs.push(z);
  const n = lampXs.length * lampZs.length;
  const housing = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.22, 0.42, 0.42, 20, 1, true), new THREE.MeshStandardMaterial({ color: 0x8a9098, metalness: 0.7, roughness: 0.3, side: THREE.DoubleSide }), n);
  const lens = new THREE.InstancedMesh(new THREE.CircleGeometry(0.4, 20), new THREE.MeshBasicMaterial({ color: 0xfffbea }), n);
  const cable = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.012, 0.012, 1.4, 4), steel, n);
  const pools = new THREE.InstancedMesh(new THREE.PlaneGeometry(5, 5), poolMat, n);
  let i = 0;
  const q = new THREE.Quaternion(), down = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI / 2), flat = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), -Math.PI / 2), one = new THREE.Vector3(1, 1, 1);
  const ly = H - 2.6 + FY;
  for (const x of lampXs) for (const z of lampZs) {
    housing.setMatrixAt(i, mm.compose(new THREE.Vector3(x, ly, z), q, one));
    lens.setMatrixAt(i, mm.compose(new THREE.Vector3(x, ly - 0.21, z), down, one));
    cable.setMatrixAt(i, mm.compose(new THREE.Vector3(x, ly + 0.9, z), q, one));
    pools.setMatrixAt(i, mm.compose(new THREE.Vector3(x, FY + 0.01, z), flat, one));
    i++;
  }
  pools.renderOrder = 1;
  g.add(housing, lens, cable, pools);

  /* ventilation duct along the back wall */
  const duct = new THREE.Mesh(new THREE.CylinderGeometry(0.38, 0.38, W - 4, 24), new THREE.MeshStandardMaterial({ color: 0xc9ced3, metalness: 0.8, roughness: 0.28 }));
  duct.rotation.z = Math.PI / 2; duct.position.set(0, H - 3.3 + FY, -D / 2 + 2.2); g.add(duct);

  /* doors: two personnel doors and a sectional gate */
  const doorMat = new THREE.MeshStandardMaterial({ color: 0x6b7178, roughness: 0.5, metalness: 0.4 });
  for (const [x, z, r] of [[-W / 2 + 0.06, -8, Math.PI / 2], [-10, -D / 2 + 0.06, 0], [10, -D / 2 + 0.06, 0]]) {
    const d = new THREE.Mesh(new THREE.BoxGeometry(1.1, 2.2, 0.08), doorMat); d.position.set(x, FY + 1.1, z); d.rotation.y = r; g.add(d);
    const bar = new THREE.Mesh(new THREE.BoxGeometry(0.8, 0.06, 0.06), new THREE.MeshStandardMaterial({ color: 0xc23a2a })); bar.position.set(0, 0.0, 0.06); d.add(bar);
  }
  const gateMap = tex(64, 256, (c, w, h) => { c.fillStyle = "#c8ccd0"; c.fillRect(0, 0, w, h); c.fillStyle = "#a7acb2"; for (let y = 0; y < h; y += 16) c.fillRect(0, y, w, 2); });
  const gate = new THREE.Mesh(new THREE.PlaneGeometry(5, 5), new THREE.MeshStandardMaterial({ map: gateMap, roughness: 0.5, metalness: 0.3 }));
  gate.position.set(W / 2 - 0.05, FY + 2.5, 8); gate.rotation.y = -Math.PI / 2; g.add(gate);

  /* zone signs, as in a real hall */
  const a2 = sign("A2"); a2.position.set(9, H - 3.4 + FY, -6); a2.rotation.y = -0.35; g.add(a2);
  const b3 = sign("B3", 1.3, 0.65); b3.position.set(-3, 5.6 + FY, -D / 2 + 0.06); g.add(b3);
  const c1 = sign("C1", 1.3, 0.65); c1.position.set(-W / 2 + 0.06, 5.6 + FY, 6); c1.rotation.y = Math.PI / 2; g.add(c1);

  scene.add(g);
  tuneEnv(g, scene);
  return g;
}

/* yellow floor marking around the kiln's footprint (call after the model is loaded) */
export function markZone(scene, object, pad = 1.3) {
  const b = new THREE.Box3().setFromObject(object);
  const x0 = b.min.x - pad, x1 = b.max.x + pad, z0 = b.min.z - pad, z1 = b.max.z + pad, w = 0.12;
  const mat = new THREE.MeshStandardMaterial({ color: 0xf2c11c, roughness: 0.5 });
  const geo = new THREE.PlaneGeometry(1, 1), gr = new THREE.Group();
  for (const [cx, cz, sx, sz] of [[(x0 + x1) / 2, z0, x1 - x0 + w, w], [(x0 + x1) / 2, z1, x1 - x0 + w, w], [x0, (z0 + z1) / 2, w, z1 - z0], [x1, (z0 + z1) / 2, w, z1 - z0]]) {
    const m = new THREE.Mesh(geo, mat); m.rotation.x = -Math.PI / 2; m.scale.set(sx, sz, 1); m.position.set(cx, FY + 0.006, cz); m.receiveShadow = true; gr.add(m);
  }
  scene.add(gr);
  return gr;
}
