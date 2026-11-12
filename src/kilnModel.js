import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { DRACOLoader } from "three/examples/jsm/loaders/DRACOLoader.js";

// kiln_v5.glb — drawing УП040.003-4 + automation package (Furnace_Model/build_kiln_v5.py). Loaded once, cloned per view.
let cache = null;
export function loadKiln() {
  if (!cache) {
    const draco = new DRACOLoader(); draco.setDecoderPath(`${import.meta.env.BASE_URL}draco/`);
    const loader = new GLTFLoader(); loader.setDRACOLoader(draco);
    cache = new Promise((res, rej) => loader.load(`${import.meta.env.BASE_URL}assets/models/kiln_v5.glb`, res, undefined, rej));
  }
  return cache.then((g) => g.scene.clone(true));
}

export function makeRenderer(mount, { shadows = true } = {}) {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.5;
  renderer.shadowMap.enabled = shadows; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  mount.appendChild(renderer.domElement);
  return renderer;
}

export function studio(scene) {
  scene.background = new THREE.Color(0x16191e);
  scene.add(new THREE.HemisphereLight(0xe6ecff, 0x2a2622, 1.5));
  const key = new THREE.DirectionalLight(0xfff3e4, 2.6);
  key.position.set(-8, 14, 10); key.castShadow = true; key.shadow.mapSize.set(2048, 2048);
  Object.assign(key.shadow.camera, { left: -10, right: 10, top: 10, bottom: -10, near: 1, far: 50 });
  scene.add(key);
  const rim = new THREE.DirectionalLight(0x9db8ff, 0.9); rim.position.set(9, 6, -10); scene.add(rim);
  const floor = new THREE.Mesh(new THREE.CircleGeometry(14, 64), new THREE.MeshStandardMaterial({ color: 0x23272e, roughness: 0.95 }));
  floor.rotation.x = -Math.PI / 2; floor.position.y = -0.21; floor.receiveShadow = true; scene.add(floor);
}

export function watch(mount, renderer, camera) {
  let visible = true;
  const resize = () => { const w = mount.clientWidth, h = mount.clientHeight; renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); };
  const ro = new ResizeObserver(resize); ro.observe(mount); resize();
  const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; }, { threshold: 0.02 }); io.observe(mount);
  return { isVisible: () => visible && !document.hidden, dispose: () => { ro.disconnect(); io.disconnect(); } };
}

export const isCut = (o) => !!(o.userData && o.userData.cutaway_hide);
