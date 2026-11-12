import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { equipment } from "./data.js";
import { isCut, loadKiln, makeRenderer, watch } from "./kilnModel.js";
import { markZone, tuneEnv, workshop } from "./workshop.js";

const ACCENT = new THREE.Color(0xff6a1a);
const flat = equipment.flatMap((g) => g.items.map((it) => ({ ...it, group: g.group })));

export function KilnExplorer() {
  const mountRef = useRef(null), api = useRef({});
  const [sel, setSel] = useState(null);
  const [cut, setCut] = useState(false);
  const [ready, setReady] = useState(false);
  const numbered = useMemo(() => flat.map((it, i) => ({ ...it, n: i + 1 })), []);

  useEffect(() => {
    const mount = mountRef.current;
    const renderer = makeRenderer(mount);
    const scene = new THREE.Scene(); workshop(scene, renderer);
    const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 200);
    const HOME = { pos: new THREE.Vector3(-8.6, 5.2, 10.4), tgt: new THREE.Vector3(0.2, 1.9, 0) };
    camera.position.copy(HOME.pos);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.copy(HOME.tgt); controls.enableDamping = true; controls.minDistance = 1.6; controls.maxDistance = 16; controls.maxPolarAngle = 1.5; controls.minPolarAngle = 0.9;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    controls.autoRotate = !reduceMotion; controls.autoRotateSpeed = 0.45;
    const w = watch(mount, renderer, camera);
    let raf, disposed = false, kiln, cutParts = [];
    const centers = {}, highlight = { meshes: [], t: 0 }, kc = new THREE.Vector3();
    let fly = null;
    const stopFly = () => { fly = null; controls.autoRotate = false; };
    renderer.domElement.addEventListener("pointerdown", stopFly);
    renderer.domElement.addEventListener("wheel", stopFly, { passive: true });

    loadKiln().then((k) => {
      if (disposed) return;
      kiln = k; scene.add(kiln); markZone(scene, kiln); tuneEnv(kiln, scene);
      kiln.traverse((o) => { if (o.isMesh) { o.castShadow = o.receiveShadow = true; } if (isCut(o)) cutParts.push(o); });
      kiln.updateMatrixWorld(true);
      new THREE.Box3().setFromObject(kiln).getCenter(kc);
      for (const it of flat) {
        const box = new THREE.Box3(), ms = [];
        kiln.traverse((o) => { if (o.isMesh && it.match.test(o.name)) { box.expandByObject(o); ms.push(o); } });
        if (!ms.length) continue;
        const sph = box.getBoundingSphere(new THREE.Sphere());
        centers[it.id] = { c: sph.center, r: Math.max(sph.radius, 0.35), top: box.max.y, meshes: ms };
      }
      setReady(true);
    });

    /* camera flight: orbit-style arc around a moving target, eased, with a slight pull-back mid-way */
    const sph = (pos, tgt) => new THREE.Spherical().setFromVector3(pos.clone().sub(tgt));
    function flyTo(pos, tgt, { dur = 1.9, spin = false } = {}) {
      const a = sph(camera.position, controls.target), b = sph(pos, tgt);
      let dθ = b.theta - a.theta; dθ = Math.atan2(Math.sin(dθ), Math.cos(dθ));          // shortest way round
      fly = { t0: performance.now(), dur: dur * 1000, a, b, dθ, tgt0: controls.target.clone(), tgt1: tgt.clone(), lift: Math.min(3, 0.25 * (a.radius + b.radius)), spin };
      controls.autoRotate = false;
    }
    function viewFor(c) {
      // look from outside the kiln towards the part: outward direction blended with the current view so the move feels natural
      const out = c.c.clone().sub(kc).setY(0);
      if (out.lengthSq() < 0.04) out.set(-0.6, 0, 1);
      out.normalize();
      const cur = camera.position.clone().sub(controls.target).setY(0).normalize();
      const dir = out.multiplyScalar(0.72).add(cur.multiplyScalar(0.28)).normalize();
      const high = c.top > kc.y + 1.2 && c.r < 2;                          // roof equipment: look a bit more from above (not tall chimneys)
      const elev = THREE.MathUtils.degToRad(high ? 34 : 20);
      const fov = THREE.MathUtils.degToRad(camera.fov) * Math.min(1, camera.aspect);
      const dist = THREE.MathUtils.clamp((c.r / Math.sin(fov / 2)) * 1.25, 2.4, 14);
      dir.multiplyScalar(Math.cos(elev)).setY(Math.sin(elev)).normalize();
      const pos = c.c.clone().addScaledVector(dir, dist);
      // stay under the lamps and above the floor; tall parts are viewed almost level, from a bit further away
      if (pos.y > 6.8) { const hz = pos.clone().sub(c.c).setY(0), k = Math.sqrt(Math.max(dist * dist - (6.8 - c.c.y) ** 2, 4)) / hz.length(); pos.copy(c.c).addScaledVector(hz, k).setY(6.8); }
      pos.y = Math.max(pos.y, 0.8);
      return pos;
    }

    function setCutaway(on) { cutParts.forEach((o) => { o.visible = !on; }); }
    function clearHighlight() {
      highlight.meshes.forEach((m) => { m.material = m.userData.baseMat; }); highlight.meshes = [];
    }
    api.current.select = (id) => {
      clearHighlight();
      if (!id || !centers[id]) { flyTo(HOME.pos, HOME.tgt, { spin: true }); return; }
      const it = flat.find((x) => x.id === id), c = centers[id];
      const pos = viewFor(c), tgt = c.c.clone();
      tgt.y -= pos.distanceTo(c.c) * 0.1;                               // keep the part above the info card
      flyTo(pos, tgt, { spin: true });
      c.meshes.forEach((m) => {
        m.userData.baseMat = m.userData.baseMat || m.material;
        const mm = m.userData.baseMat.clone(); mm.emissive = ACCENT.clone(); mm.emissiveIntensity = 0.5; m.material = mm; highlight.meshes.push(m);
      });
      if (it.cut) { setCutaway(true); api.current.onCut?.(true); }
    };
    api.current.cut = (on) => setCutaway(on);
    api.current.home = () => { clearHighlight(); flyTo(HOME.pos, HOME.tgt, { spin: true }); };

    const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
    function frame() {
      raf = requestAnimationFrame(frame);
      if (!w.isVisible()) return;
      if (fly) {
        const t = Math.min((performance.now() - fly.t0) / fly.dur, 1), k = ease(t);
        controls.target.lerpVectors(fly.tgt0, fly.tgt1, k);
        const s = new THREE.Spherical(
          THREE.MathUtils.lerp(fly.a.radius, fly.b.radius, k) + Math.sin(Math.PI * k) * fly.lift,
          THREE.MathUtils.lerp(fly.a.phi, fly.b.phi, k),
          fly.a.theta + fly.dθ * k);
        camera.position.setFromSpherical(s).add(controls.target);
        if (t >= 1) { controls.autoRotate = fly.spin && !reduceMotion; controls.autoRotateSpeed = 0.35; fly = null; }
      }
      highlight.t += 0.05;
      highlight.meshes.forEach((m) => { m.material.emissiveIntensity = 0.25 + 0.25 * Math.sin(highlight.t * 2); });
      controls.update();
      renderer.render(scene, camera);
    }
    frame();
    return () => { disposed = true; cancelAnimationFrame(raf); w.dispose(); controls.dispose(); renderer.dispose(); mount.removeChild(renderer.domElement); };
  }, []);

  useEffect(() => { api.current.onCut = setCut; }, []);
  const choose = (id) => { const next = sel === id ? null : id; setSel(next); api.current.select?.(next); };
  const toggleCut = () => { const on = !cut; setCut(on); api.current.cut?.(on); };
  const cur = numbered.find((x) => x.id === sel);

  return (
    <div className="explorer">
      <div className="stage" data-hide>
        <div className="stage-canvas" ref={mountRef} role="img" aria-label="Интерактивная 3D-модель печи USM с автоматикой и навесным оборудованием" />
        {!ready && <div className="stage-loading">Загружаем модель печи…</div>}
        <div className="stage-tools">
          <button className={cut ? "tool on" : "tool"} onClick={toggleCut} aria-pressed={cut}>Разрез</button>
          <button className="tool" onClick={() => { setSel(null); api.current.home?.(); }}>Общий вид</button>
        </div>
        {cur && (
          <div className="stage-card" role="status">
            <span className="stage-card-n">{String(cur.n).padStart(2, "0")} · {cur.group}</span>
            <strong>{cur.title}</strong>
            <p>{cur.text}</p>
          </div>
        )}
      </div>
      <nav className="eq-list" aria-label="Узлы и оборудование печи">
        {equipment.map((g) => (
          <div key={g.group} className="eq-group">
            <span className="eq-group-name">{g.group}</span>
            {g.items.map((it) => {
              const n = numbered.find((x) => x.id === it.id).n;
              return (
                <button key={it.id} className={sel === it.id ? "eq on" : "eq"} onClick={() => choose(it.id)} aria-pressed={sel === it.id}>
                  <span className="eq-n">{String(n).padStart(2, "0")}</span><span>{it.title}</span>
                </button>
              );
            })}
          </div>
        ))}
      </nav>
    </div>
  );
}
