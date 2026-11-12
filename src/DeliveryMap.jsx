import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { DRACOLoader } from "three/examples/jsm/loaders/DRACOLoader.js";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/examples/jsm/postprocessing/OutputPass.js";
import { CITIES, MAP_THICK, REGION_NAMES, project } from "./geo.js";
import { useOffer } from "./Picker.jsx";

const name = (code) => REGION_NAMES[code] || "";

/* 2D raster of the map: which region covers (x, z) — used for hover, for keeping lights on land and beacons in their region */
function buildMask(tops, res = 0.006) {
  const box = new THREE.Box3(); tops.forEach(({ mesh }) => box.expandByObject(mesh));
  const W = Math.ceil((box.max.x - box.min.x) / res) + 1, H = Math.ceil((box.max.z - box.min.z) / res) + 1;
  const grid = new Int16Array(W * H).fill(-1);
  const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3();
  tops.forEach(({ mesh }, ri) => {
    const g = mesh.geometry, pos = g.attributes.position, idx = g.index, n = idx ? idx.count : pos.count;
    mesh.updateWorldMatrix(true, false);
    for (let i = 0; i < n; i += 3) {
      const i0 = idx ? idx.getX(i) : i, i1 = idx ? idx.getX(i + 1) : i + 1, i2 = idx ? idx.getX(i + 2) : i + 2;
      a.fromBufferAttribute(pos, i0).applyMatrix4(mesh.matrixWorld); b.fromBufferAttribute(pos, i1).applyMatrix4(mesh.matrixWorld); c.fromBufferAttribute(pos, i2).applyMatrix4(mesh.matrixWorld);
      const x0 = Math.floor((Math.min(a.x, b.x, c.x) - box.min.x) / res), x1 = Math.ceil((Math.max(a.x, b.x, c.x) - box.min.x) / res);
      const z0 = Math.floor((Math.min(a.z, b.z, c.z) - box.min.z) / res), z1 = Math.ceil((Math.max(a.z, b.z, c.z) - box.min.z) / res);
      const d = (b.z - c.z) * (a.x - c.x) + (c.x - b.x) * (a.z - c.z); if (Math.abs(d) < 1e-12) continue;
      for (let gz = z0; gz <= z1; gz++) for (let gx = x0; gx <= x1; gx++) {
        const px = box.min.x + gx * res, pz = box.min.z + gz * res;
        const l1 = ((b.z - c.z) * (px - c.x) + (c.x - b.x) * (pz - c.z)) / d, l2 = ((c.z - a.z) * (px - c.x) + (a.x - c.x) * (pz - c.z)) / d;
        if (l1 >= -0.01 && l2 >= -0.01 && l1 + l2 <= 1.01 && gx >= 0 && gz >= 0 && gx < W && gz < H) grid[gz * W + gx] = ri;
      }
    }
  });
  return { raster: { grid, W, H, res, x0: box.min.x, z0: box.min.z }, at: (x, z) => { const gx = Math.round((x - box.min.x) / res), gz = Math.round((z - box.min.z) / res); return gx < 0 || gz < 0 || gx >= W || gz >= H ? -1 : grid[gz * W + gx]; },
    centroid: (ri) => { let sx = 0, sz = 0, n = 0; for (let i = 0; i < grid.length; i++) if (grid[i] === ri) { sx += i % W; sz += Math.floor(i / W); n++; } return n ? [box.min.x + (sx / n) * res, box.min.z + (sz / n) * res] : [0, 0]; } };
}

/* soft additive point lights with per-point size, brightness and a slow twinkle */
function lightsMaterial() {
  return new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, toneMapped: false,
    uniforms: { uTime: { value: 0 }, uScale: { value: 1 } },
    vertexShader: `attribute float size; attribute float bright; attribute float seed; varying float vB; uniform float uTime; uniform float uScale;
      void main(){ vec4 mv = modelViewMatrix * vec4(position,1.0); vB = bright * (0.82 + 0.18*sin(uTime*1.7 + seed*40.0));
      gl_PointSize = size * uScale / -mv.z; gl_Position = projectionMatrix * mv; }`,
    fragmentShader: `varying float vB; void main(){ vec2 d = gl_PointCoord - 0.5; float r = length(d); if (r > 0.5) discard;
      float core = smoothstep(0.5, 0.0, r); vec3 col = mix(vec3(1.0,0.45,0.12), vec3(1.0,0.86,0.55), core*core);
      gl_FragColor = vec4(col * vB * core * 1.6, core * vB); }`,
  });
}

/* glowing outline of the whole country: crisp edge on top of the map + soft blurred glow under it */
function outlineTextures(m) {
  const pad = 150, W = m.W + pad * 2, H = m.H + pad * 2;
  const solid = document.createElement("canvas"); solid.width = W; solid.height = H;
  const edge = document.createElement("canvas"); edge.width = W; edge.height = H;
  const si = solid.getContext("2d").createImageData(W, H), ei = edge.getContext("2d").createImageData(W, H);
  const id = (x, y) => (x >= 0 && y >= 0 && x < m.W && y < m.H ? m.grid[y * m.W + x] : -1), land = (x, y) => id(x, y) >= 0;
  const border = document.createElement("canvas"); border.width = W; border.height = H;
  const bi = border.getContext("2d").createImageData(W, H);
  for (let y = 0; y < m.H; y++) for (let x = 0; x < m.W; x++) {
    if (!land(x, y)) continue;
    const o = ((y + pad) * W + x + pad) * 4;
    si.data[o] = 255; si.data[o + 1] = 140; si.data[o + 2] = 50; si.data[o + 3] = 255;
    if (!land(x - 1, y) || !land(x + 1, y) || !land(x, y - 1) || !land(x, y + 1)) { ei.data[o] = 255; ei.data[o + 1] = 196; ei.data[o + 2] = 120; ei.data[o + 3] = 255; }
    else if (id(x + 1, y) !== id(x, y) || id(x, y + 1) !== id(x, y)) { bi.data[o] = 120; bi.data[o + 1] = 126; bi.data[o + 2] = 136; bi.data[o + 3] = 255; }   // border between two regions
  }
  solid.getContext("2d").putImageData(si, 0, 0); edge.getContext("2d").putImageData(ei, 0, 0); border.getContext("2d").putImageData(bi, 0, 0);
  const glow = document.createElement("canvas"); glow.width = W; glow.height = H;
  const g = glow.getContext("2d");
  g.filter = "blur(30px)"; g.globalAlpha = 0.9; g.drawImage(solid, 0, 0);
  g.filter = "blur(9px)"; g.globalAlpha = 1; g.drawImage(edge, 0, 0); g.drawImage(edge, 0, 0); g.drawImage(edge, 0, 0);
  const line = document.createElement("canvas"); line.width = W; line.height = H;
  const l = line.getContext("2d"); l.globalAlpha = 0.85; l.filter = "blur(0.5px)"; l.drawImage(border, 0, 0); l.globalAlpha = 1;
  l.filter = "blur(1.2px)"; l.drawImage(edge, 0, 0); l.drawImage(edge, 0, 0); l.filter = "none"; l.drawImage(edge, 0, 0);
  const tex = (c) => { const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t; };
  return { glow: tex(glow), line: tex(line), w: W * m.res, h: H * m.res, cx: m.x0 - pad * m.res + (W * m.res) / 2, cz: m.z0 - pad * m.res + (H * m.res) / 2 };
}

export function DeliveryMap() {
  const { open } = useOffer();
  const mountRef = useRef(null), tipRef = useRef(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const mount = mountRef.current;
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, window.innerWidth < 800 ? 1.5 : 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace; renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.05;
    mount.appendChild(renderer.domElement);
    const scene = new THREE.Scene(); scene.background = new THREE.Color(0x090a0c);
    // flat map, seen straight from above
    const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 100);
    camera.position.set(0, 30, 0); camera.up.set(0, 0, -1); camera.lookAt(0, 0, 0);
    scene.add(new THREE.HemisphereLight(0xb7c3d6, 0x0a0a0c, 0.9));
    const key = new THREE.DirectionalLight(0xffe2c4, 0.6); key.position.set(-4, 10, 3); scene.add(key);

    const composer = new EffectComposer(renderer);
    composer.addPass(new RenderPass(scene, camera));
    const bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), 0.75, 0.55, 0.5); composer.addPass(bloom);
    composer.addPass(new OutputPass());
    const lightsMat = lightsMaterial();
    let fitBox = null;
    const resize = () => {
      const w = mount.clientWidth, h = mount.clientHeight; renderer.setSize(w, h, false); composer.setSize(w, h); bloom.resolution.set(w, h);
      const bx = fitBox || { x0: -5.2, x1: 5.2, z0: -3.6, z1: 3.6 };
      const cx = (bx.x0 + bx.x1) / 2, cz = (bx.z0 + bx.z1) / 2, aw = (bx.x1 - bx.x0) * 1.12, ah = (bx.z1 - bx.z0) * 1.14;   // room for the glow on every side
      const a = w / h, halfW = Math.max(aw, ah * a) / 2, halfH = halfW / a;
      Object.assign(camera, { left: -halfW, right: halfW, top: halfH, bottom: -halfH });   // frustum is relative to the camera
      camera.position.set(cx, 30, cz); camera.lookAt(cx, 0, cz); camera.updateProjectionMatrix();
      lightsMat.uniforms.uScale.value = 30 * renderer.getPixelRatio() * (w / (halfW * 2)) * 0.03;   // dots scale with the map
    };
    const ro = new ResizeObserver(resize); ro.observe(mount); resize();
    let visible = true; const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; }, { threshold: 0.02 }); io.observe(mount);

    const topMat = new THREE.MeshStandardMaterial({ color: 0x15171b, roughness: 0.8, metalness: 0.2 });
    const hoverMat = new THREE.MeshStandardMaterial({ color: 0x2a221c, roughness: 0.6, metalness: 0.2, emissive: 0xff6a1a, emissiveIntensity: 0.08 });
    let disposed = false, raf, mask = null, tops = [], hovered = -1;
    const draco = new DRACOLoader(); draco.setDecoderPath(`${import.meta.env.BASE_URL}draco/`);
    const loader = new GLTFLoader(); loader.setDRACOLoader(draco);
    loader.load(`${import.meta.env.BASE_URL}assets/models/russia_map.glb`, (gltf) => {
      if (disposed) return;
      const root = gltf.scene; scene.add(root);
      root.traverse((o) => {
        if (!o.isMesh) return;
        let n = o; while (n && !/^(RU|UA)/.test(n.name)) n = n.parent;
        const code = n ? (n.name.match(/^RU([A-Z]+)/) || [, n.name])[1] : "";
        if (!/top/.test(o.material.name)) { o.visible = false; return; }        // flat map: only the region faces
        o.material = topMat; tops.push({ mesh: o, code });
      });
      root.updateMatrixWorld(true);
      mask = buildMask(tops);
      const r = mask.raster; fitBox = { x0: r.x0, x1: r.x0 + r.W * r.res, z0: r.z0, z1: r.z0 + r.H * r.res }; resize();

      // glowing outline: soft glow under the map, crisp line on top
      const t = outlineTextures(r);
      const plane = (map, y, opacity) => { const m = new THREE.Mesh(new THREE.PlaneGeometry(t.w, t.h), new THREE.MeshBasicMaterial({ map, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, toneMapped: false, opacity }));
        m.rotation.x = -Math.PI / 2; m.position.set(t.cx, y, t.cz); scene.add(m); return m; };
      plane(t.glow, -0.01, 0.85).renderOrder = -1;
      plane(t.line, MAP_THICK + 0.006, 1).renderOrder = 4;

      // city lights: bright cores + scattered settlements, only on land
      const P = [], S = [], B = [], R = [];
      let s = 7; const rnd = () => ((s = (s * 16807) % 2147483647) / 2147483647);
      const gauss = () => Math.sqrt(-2 * Math.log(rnd() + 1e-9)) * Math.cos(2 * Math.PI * rnd());
      const put = (x, z, size, b) => { if (mask.at(x, z) < 0) return; P.push(x, MAP_THICK + 0.01, z); S.push(size); B.push(b); R.push(rnd()); };
      CITIES.forEach(([, la, lo, pop]) => {
        const [x, z] = project(la, lo), lp = Math.log10(Math.max(pop, 5));
        put(x, z, 1.2 + 1.2 * (lp - 1), 0.95 + 0.2 * (lp - 1));
        const n = Math.min(60, Math.round(6 + Math.sqrt(pop) / 2.6)), sig = 0.16 + 0.12 * lp;
        for (let i = 0; i < n; i++) { const [sx, sz] = project(la + gauss() * sig * 0.55, lo + gauss() * sig); put(sx, sz, 0.35 + rnd() * 0.5, 0.3 + rnd() * 0.4); }
      });
      const lg = new THREE.BufferGeometry();
      lg.setAttribute("position", new THREE.Float32BufferAttribute(P, 3)); lg.setAttribute("size", new THREE.Float32BufferAttribute(S, 1));
      lg.setAttribute("bright", new THREE.Float32BufferAttribute(B, 1)); lg.setAttribute("seed", new THREE.Float32BufferAttribute(R, 1));
      const lights = new THREE.Points(lg, lightsMat); lights.frustumCulled = false; lights.renderOrder = 5; scene.add(lights);
      setReady(true);
    });

    /* hover: region name */
    const ray = new THREE.Raycaster(), ndc = new THREE.Vector2(), plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -MAP_THICK), hit = new THREE.Vector3();
    const onMove = (e) => {
      if (!mask) return;
      const rc = renderer.domElement.getBoundingClientRect();
      ndc.set(((e.clientX - rc.left) / rc.width) * 2 - 1, -((e.clientY - rc.top) / rc.height) * 2 + 1);
      ray.setFromCamera(ndc, camera);
      const ri = ray.ray.intersectPlane(plane, hit) ? mask.at(hit.x, hit.z) : -1, tip = tipRef.current;
      if (ri !== hovered) { if (hovered >= 0) tops[hovered].mesh.material = topMat; hovered = ri; if (ri >= 0) tops[ri].mesh.material = hoverMat; }
      const label = ri >= 0 ? name(tops[ri].code) : "";
      if (!tip) return;
      if (!label) { tip.style.opacity = "0"; return; }
      tip.textContent = label;
      tip.style.transform = `translate(${e.clientX - rc.left + 14}px, ${e.clientY - rc.top + 14}px)`; tip.style.opacity = "1";
    };
    const onLeave = () => { if (tipRef.current) tipRef.current.style.opacity = "0"; if (hovered >= 0) tops[hovered].mesh.material = topMat; hovered = -1; };
    renderer.domElement.addEventListener("pointermove", onMove);
    renderer.domElement.addEventListener("pointerleave", onLeave);

    const clock = new THREE.Clock(); let t = 0;
    const frame = () => {
      raf = requestAnimationFrame(frame);
      const dt = Math.min(clock.getDelta(), 0.05);
      if (!visible || document.hidden) return;
      t += dt; lightsMat.uniforms.uTime.value = t;
      composer.render();
    };
    frame();
    return () => {
      disposed = true; cancelAnimationFrame(raf); ro.disconnect(); io.disconnect();
      renderer.domElement.removeEventListener("pointermove", onMove); renderer.domElement.removeEventListener("pointerleave", onLeave);
      composer.dispose(); renderer.dispose(); mount.removeChild(renderer.domElement);
    };
  }, []);

  return (
    <div className="geo-grid">
      <div className="geo-main">
        <div className="geo-stage" data-hide>
          <div className="geo-canvas" ref={mountRef} role="img" aria-label="Карта России: поставки во все регионы, светящиеся точки — города" />
          {!ready && <div className="stage-loading">Загружаем карту…</div>}
          <div className="geo-tip" ref={tipRef} aria-hidden="true" />
        </div>
        <p className="geo-note">Карта: Mike / Sketchfab, CC BY 4.0; восток Чукотки — Natural Earth.</p>
      </div>
      <aside className="geo-card" data-edge>
        <span className="geo-k">Результаты работы</span>
        <div className="geo-big" data-perch>40<span>+</span></div>
        <p className="geo-big-l">печей продано<br />нашим клиентам</p>
        <div className="geo-row">
          <div><strong>РФ</strong><span>все регионы<br />России</span></div>
          <div><strong>Экспорт</strong><span>отправляем<br />и за рубеж</span></div>
        </div>
        <div className="geo-cta">
          <h3 data-perch>Обсудим доставку в ваш регион</h3>
          <p>Укажите населённый пункт и нужную комплектацию — согласуем логистику и сроки поставки.</p>
          <button className="btn btn-fire full" onClick={() => open(["Доставка в ваш регион"])}>Обсудить доставку <span aria-hidden="true">→</span></button>
        </div>
      </aside>
    </div>
  );
}
