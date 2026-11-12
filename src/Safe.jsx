import { Component, useEffect, useRef, useState } from "react";

/* three r162 runs on WebGL 2 and falls back to WebGL 1. `?no3d` forces the fallback (for testing). */
let gl3D = null;
export function has3D() {
  if (gl3D !== null) return gl3D;
  try {
    if (new URLSearchParams(location.search).has("no3d")) return (gl3D = false);
    const c = document.createElement("canvas");
    const ctx = c.getContext("webgl2") || c.getContext("webgl") || c.getContext("experimental-webgl");
    ctx?.getExtension("WEBGL_lose_context")?.loseContext();          // free the probe (iOS limits GL contexts)
    gl3D = !!ctx;
  } catch { gl3D = false; }
  return gl3D;
}

/* One broken block must never blank the whole page: catch it and show a fallback instead. */
export class Boundary extends Component {
  constructor(p) { super(p); this.state = { error: null }; }
  static getDerivedStateFromError(error) { return { error }; }
  componentDidCatch(error) { console.error("[USM] block failed:", error); }
  render() { return this.state.error ? (this.props.fallback ?? null) : this.props.children; }
}

/* Mount heavy 3D only when it is about to scroll into view — fewer GPU contexts and less memory on phones. */
export function NearView({ children, placeholder, margin = "600px" }) {
  const ref = useRef(null);
  const [on, setOn] = useState(false);
  useEffect(() => {
    const el = ref.current; if (!el) return;
    if (!("IntersectionObserver" in window)) { setOn(true); return; }
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setOn(true); io.disconnect(); } }, { rootMargin: margin });
    io.observe(el); return () => io.disconnect();
  }, [margin]);
  return <div ref={ref}>{on ? children : placeholder}</div>;
}

/* What the reader sees when 3D is unavailable on the device */
export function NoGL({ title, text, img }) {
  return (
    <div className="nogl">
      {img && <img src={img} alt="" loading="lazy" />}
      <div><strong>{title}</strong><p>{text}</p></div>
    </div>
  );
}
