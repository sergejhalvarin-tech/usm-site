import { useEffect, useRef, useState } from "react";
import { MascotSprite } from "./Brand.jsx";
import { tips } from "./data.js";

/* «Огонёк» — the USM mascot, drawn from the same layered flame as the logo. Lives in page coordinates on a layer below headings
   (z-index 1 < 2), so it can stand on the letters, run along a line, dip behind the glyphs and hide behind the kiln.
   Motion is physical: anticipation crouch → ballistic flight under gravity (stretch + tilt) → landing squash with dust;
   running accelerates and brakes. Idle life: waves, dances, sits and swings its legs, yawns, sends hearts, falls asleep,
   follows the cursor with its eyes, gets shy when hovered and happy when clicked. */
const FOOT = 54;            // px from sprite top to feet
const G = 2600;             // px/s² — gravity
const RUN = 120, ACC = 900; // px/s, px/s²
const SLEEP_AFTER = 16;     // s without any user activity

function lineRects(el) {
  const r = document.createRange(); r.selectNodeContents(el);
  const rects = [...r.getClientRects()].filter((q) => q.width > 8 && q.height > 8);
  const lines = [];
  for (const q of rects) {
    const l = lines.find((x) => Math.abs(x.top - q.top) < 6);
    if (l) { l.left = Math.min(l.left, q.left); l.right = Math.max(l.right, q.right); l.h = Math.max(l.h, q.height); }
    else lines.push({ top: q.top, left: q.left, right: q.right, h: q.height });
  }
  return lines;
}

export function Mascot() {
  const ref = useRef(null), spriteRef = useRef(null), layerRef = useRef(null);
  const [view, setView] = useState({ pose: "idle", mood: "smile", blink: false, lookX: 0, lookY: 0, flip: false, bubble: null });
  const st = useRef(null);

  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const s = st.current = { x: 120, y: 200, vx: 0, vy: 0, mode: "idle", t: 0, dur: 1.2, perch: null, flip: false, seen: new Set(),
      pose: "idle", mood: "smile", nextBlink: 2, bubbleUntil: 0, bubble: null, sx: 1, sy: 1, rot: 0, lastUser: performance.now() / 1000, hover: false };
    const sxp = () => window.scrollX, syp = () => window.scrollY;
    const setLayer = (z) => { const l = layerRef.current; if (l) { l.style.zIndex = z; l.classList.toggle("floating", z > 1); } };
    const now = () => performance.now() / 1000;

    /* little particles (dust, hearts, z, sparks) — DOM, CSS-animated, self-removing */
    function fx(type, x, y, n = 1) {
      const layer = layerRef.current; if (!layer || reduce) return;
      for (let i = 0; i < n; i++) {
        const e = document.createElement("span");
        e.className = `og-fx og-fx-${type}`;
        e.textContent = type === "heart" ? "♥" : type === "z" ? "z" : "";
        const dx = type === "dust" ? (i % 2 ? 1 : -1) * (8 + Math.random() * 10) : (Math.random() - 0.5) * 22;
        e.style.left = `${x}px`; e.style.top = `${y}px`; e.style.setProperty("--dx", `${dx}px`); e.style.setProperty("--d", `${0.6 + Math.random() * 0.5}s`);
        e.addEventListener("animationend", () => e.remove());
        layer.appendChild(e);
      }
    }

    function edgePerch(el) {
      const r = el.getBoundingClientRect();
      return { el, edge: true, big: false, y: r.top + syp(), x0: r.left + 26 + sxp(), x1: r.right - 26 + sxp(), h: 0 };
    }
    function perches() {
      const vh = window.innerHeight, out = [];
      if (s.float && s.float.isConnected) {          // a dropdown / dialog is open: stay on it
        out.push(edgePerch(s.float));
        s.float.querySelectorAll("[data-perch]").forEach((el) => {
          for (const l of lineRects(el)) out.push({ el, big: false, y: l.top + l.h * 0.12 + syp(), x0: l.left + 12 + sxp(), x1: Math.max(l.left + 14, l.right - 12) + sxp(), h: l.h });
        });
        return out;
      }
      document.querySelectorAll("[data-edge]").forEach((el) => {
        const r = el.getBoundingClientRect();
        if (r.top > 80 && r.top < vh * 0.86) out.push(edgePerch(el));
      });
      document.querySelectorAll("[data-perch]").forEach((el) => {
        if (el.closest("[data-float]")) return;
        const big = parseFloat(getComputedStyle(el).fontSize) >= 30;
        for (const l of lineRects(el)) {
          if (l.top < 70 || l.top > vh * 0.86 || l.right - l.left < 50) continue;
          const top = l.top + l.h * (big ? 0.2 : 0.12);
          out.push({ el, big, y: top + syp(), x0: l.left + 16 + sxp(), x1: l.right - 16 + sxp(), h: l.h });
        }
      });
      return out;
    }
    function hideSpots() {
      const out = [];
      document.querySelectorAll("[data-hide]").forEach((el) => {
        const r = el.getBoundingClientRect();
        if (r.bottom < 90 || r.top > window.innerHeight - 40) return;
        out.push({ x0: r.left + r.width * 0.25 + sxp(), x1: r.left + r.width * 0.75 + sxp(), y: r.top + r.height * 0.62 + syp() });
      });
      return out;
    }
    const pick = (a) => a[(Math.random() * a.length) | 0];
    function sectionTip() {
      const y = s.y - syp();
      let best = null, bd = 1e9;
      document.querySelectorAll("section[id]").forEach((sec) => {
        const r = sec.getBoundingClientRect();
        const d = y < r.top ? r.top - y : y > r.bottom ? y - r.bottom : 0;
        if (d < bd) { bd = d; best = sec.id; }
      });
      return best;
    }
    function say(text, sec = 3.6) { s.bubble = text; s.bubbleUntil = now() + sec; }
    const setMode = (mode, dur = 1, pose = mode, mood = "smile") => { s.mode = mode; s.t = 0; s.dur = dur; s.pose = pose; s.mood = mood; };

    /* jump = anticipation crouch, then a real ballistic arc that lands exactly on the target */
    function jumpTo(x, y, perch, after = null) {
      s.jump = { x, y, perch, after }; s.flip = x < s.x;
      setMode("crouch", 0.12, "crouch", s.mood === "sleep" ? "wow" : "smile");
    }
    function launch() {
      const { x, y } = s.jump, dist = Math.hypot(x - s.x, y - s.y);
      const h = Math.min(230, 34 + dist * 0.2), apex = Math.min(s.y, y) - h;
      s.vy = -Math.sqrt(2 * G * (s.y - apex));
      const T = -s.vy / G + Math.sqrt((2 * (y - apex)) / G);
      s.vx = (x - s.x) / T; s.T = T;
      setMode("air", T, "air");
    }
    function land() {
      const j = s.jump; s.x = j.x; s.y = j.y; s.perch = j.perch;
      const impact = Math.abs(s.vy); s.vx = s.vy = 0;
      if (impact > 420) fx("dust", s.x, s.y, 2);
      s.squash = Math.min(0.32, impact / 4200);
      if (j.after === "lurk") { setMode("lurk", 2.5 + Math.random() * 2, "hide"); return; }
      setMode("land", 0.18, "land", s.mood);
    }

    /* idle life: what to do next */
    function decide() {
      const ps = perches(), vh = window.innerHeight;
      const onScreen = s.y - syp() > 60 && s.y - syp() < vh - 10;
      const stillOnPerch = s.perch && ps.some((p) => p.el === s.perch.el && Math.abs(p.y - s.perch.y) < 6);
      if (s.perch && stillOnPerch) s.perch = ps.find((p) => p.el === s.perch.el && Math.abs(p.y - s.perch.y) < 6);
      if (!ps.length) {
        const y = syp() + vh - 18, x = sxp() + 34 + Math.random() * 60;
        if (!onScreen) { s.x = x; s.y = syp() + vh + 60; }
        jumpTo(x, y, null); return;
      }
      if (!onScreen || !stillOnPerch) {
        const target = ps.reduce((a, b) => (Math.abs(b.y - syp() - vh * 0.35) < Math.abs(a.y - syp() - vh * 0.35) ? b : a));
        if (!onScreen) { s.x = Math.min(Math.max(target.x0, sxp() + 40), sxp() + window.innerWidth - 40); s.y = s.y < syp() ? syp() + 40 : syp() + vh + 40; }
        jumpTo(target.x0 + Math.random() * (target.x1 - target.x0), target.y, target);
        const sec = sectionTip();
        if (sec && !s.seen.has(sec) && tips[sec]) { s.seen.add(sec); setTimeout(() => say(tips[sec]), 900); }
        return;
      }
      if (now() - s.lastUser > SLEEP_AFTER) { setMode("sleep", 1e9, "sleep", "sleep"); s.nextZ = now() + 0.6; return; }
      const r = Math.random(), p = s.perch;
      if (s.float) {
        if (r < 0.5 && p.x1 - p.x0 > 40) { s.mode = "walk"; s.to = p.x0 + Math.random() * (p.x1 - p.x0); s.flip = s.to < s.x; }
        else if (r < 0.7 && ps.length > 1) { const q = pick(ps.filter((x) => x !== p)); jumpTo(q.x0 + Math.random() * (q.x1 - q.x0), q.y, q); }
        else if (r < 0.85) setMode("wave", 1.6, "wave", "happy");
        else setMode("idle", 1, "idle");
        return;
      }
      if (r < 0.3 && p.x1 - p.x0 > 60) { s.mode = "walk"; s.to = p.x0 + Math.random() * (p.x1 - p.x0); s.flip = s.to < s.x; }
      else if (r < 0.47 && ps.length > 1) {
        const others = ps.filter((q) => q !== p && Math.abs(q.y - p.y) < vh * 0.6);
        const q = others.length ? pick(others) : pick(ps);
        jumpTo(q.x0 + Math.random() * (q.x1 - q.x0), q.y, q);
      }
      else if (r < 0.56) setMode("wave", 1.8, "wave", "happy");
      else if (r < 0.63) { setMode("dance", 2.6, "dance", "happy"); s.hops = 0; }
      else if (r < 0.71) setMode("sit", 3.5 + Math.random() * 2.5, "sit", "smile");
      else if (r < 0.76) setMode("yawn", 1.6, "yawn", "wow");
      else if (r < 0.82) { setMode("love", 1.8, "idle", "love"); fx("heart", s.x, s.y - 50, 3); }
      else if (r < 0.88 && p.big) { setMode("hide", 2.4 + Math.random() * 1.5, "hide"); s.depth = p.h * 0.5; }
      else if (r < 0.94 && hideSpots().length) {
        const h = pick(hideSpots());
        s.back = { x: s.x, y: s.y, perch: p }; jumpTo(h.x0 + Math.random() * (h.x1 - h.x0), h.y, null, "lurk");
      } else setMode("idle", 1 + Math.random() * 2, "idle");
    }

    const onFocus = (e) => {
      const el = e.detail?.el; if (!el) return;
      s.stack = (s.stack || []).filter((x) => x !== el && x.isConnected);
      if (s.float && s.float !== el && s.float.isConnected) s.stack.push(s.float);
      s.float = el; setLayer(60);
      const p = edgePerch(el);
      if (s.y - syp() < 0 || s.y - syp() > window.innerHeight) { s.x = p.x0; s.y = syp() + window.innerHeight + 40; }
      s.yOff = 0;
      jumpTo(p.x0 + Math.random() * (p.x1 - p.x0), p.y, p);
      if (e.detail.tip) say(e.detail.tip, 3.4);
    };
    const onRelease = () => {
      if (!s.float) return;
      const back = (s.stack || []).filter((x) => x.isConnected).pop();
      s.stack = [];
      if (back) { onFocus({ detail: { el: back } }); return; }
      s.float = null; s.perch = null; setLayer(1);
      setMode("idle", 0.05, "idle");
    };
    window.addEventListener("ogonek:focus", onFocus);
    window.addEventListener("ogonek:release", onRelease);

    /* the user: eyes follow the pointer; any activity wakes it up */
    const ptr = { x: -1, y: -1 };
    const wake = () => {
      s.lastUser = now();
      if (s.mode === "sleep") { setMode("wake", 0.9, "yawn", "wow"); fx("spark", s.x, s.y - 40, 3); }
    };
    const onPtr = (e) => { ptr.x = e.clientX + sxp(); ptr.y = e.clientY + syp(); wake(); };
    window.addEventListener("pointermove", onPtr, { passive: true });
    window.addEventListener("scroll", wake, { passive: true });
    window.addEventListener("keydown", wake);
    s.onHover = (on) => { s.hover = on; if (on) wake(); };
    s.onClick = () => {
      wake();
      const sec = sectionTip();
      say(tips[sec] || tips.top, 4);
      fx("heart", s.x, s.y - 52, 4);
      if (s.mode !== "air" && s.mode !== "crouch") jumpTo(s.x, s.y, s.perch);
      s.mood = "happy";
    };

    setTimeout(() => {
      const ps = perches();
      if (ps.length) { s.perch = ps[0]; s.x = ps[0].x0 + 30; s.y = ps[0].y; }
      if (!reduce) { say(tips.top, 4.5); setMode("wave", 2, "wave", "happy"); }
      s.seen.add("top");
    }, 500);

    let raf, last = performance.now(), lastView = null;
    function frame(nowMs) {
      raf = requestAnimationFrame(frame);
      const dt = Math.min((nowMs - last) / 1000, 0.05); last = nowMs;
      if (document.hidden) return;
      const tn = nowMs / 1000;
      let sx = 1, sy = 1, rot = 0, yOff = s.yOff || 0;
      if (!reduce) {
        s.t += dt;
        switch (s.mode) {
          case "walk": {                                   // accelerate, cruise, brake to stop on the spot
            const d = s.to - s.x, want = Math.sign(d) * Math.min(RUN, Math.sqrt(2 * ACC * Math.abs(d)));
            s.vx += Math.max(-ACC * dt, Math.min(ACC * dt, want - s.vx));
            s.x += s.vx * dt; s.pose = "run"; rot = s.vx / RUN * 6;
            if (Math.abs(d) < 1.5 && Math.abs(s.vx) < 20) { s.x = s.to; s.vx = 0; setMode("idle", 0.6 + Math.random() * 1.4, "idle"); }
            break;
          }
          case "crouch": sy = 1 - 0.22 * Math.sin(Math.min(1, s.t / s.dur) * Math.PI / 2); sx = 2 - sy; if (s.t >= s.dur) launch(); break;
          case "air": {
            s.vy += G * dt; s.x += s.vx * dt; s.y += s.vy * dt;
            const st = Math.min(0.24, Math.abs(s.vy) / 2600); sy = 1 + st; sx = 1 - st * 0.6; rot = Math.max(-14, Math.min(14, s.vx / 40));
            if (s.t >= s.T) land();
            break;
          }
          case "land": { const k = s.t / s.dur; const q = (s.squash || 0.15) * Math.sin((1 - k) * Math.PI / 2); sy = 1 - q; sx = 1 + q * 0.8; if (k >= 1) setMode("idle", 0.5 + Math.random() * 1.2, "idle"); break; }
          case "hide": { const k = s.t / s.dur, dip = k < 0.15 ? k / 0.15 : k > 0.8 ? (1 - k) / 0.2 : 1; yOff = s.depth * Math.max(0, dip); s.pose = "hide"; if (k >= 1) { yOff = 0; setMode("idle", 0.8, "idle"); } break; }
          case "lurk": s.pose = "hide"; if (s.t >= s.dur && s.back) { const b = s.back; s.back = null; jumpTo(b.x, b.y, b.perch); } break;
          case "dance": {                                  // little hops in place under gravity
            if (!s.hopV && s.t < s.dur - 0.3) { s.hopV = -380; }
            if (s.hopV) { s.hopY = (s.hopY || 0) + s.hopV * dt; s.hopV += G * dt; if (s.hopY >= 0) { s.hopY = 0; s.hopV = 0; s.flip = !s.flip; } }
            yOff = s.hopY || 0; rot = Math.sin(s.t * 12) * 6;
            if (s.t >= s.dur) { s.hopY = 0; setMode("idle", 0.6, "idle"); }
            break;
          }
          case "sleep": sy = 1 + 0.03 * Math.sin(tn * 2); if (tn > s.nextZ) { fx("z", s.x + (s.flip ? -14 : 14), s.y - 52); s.nextZ = tn + 1.1; } break;
          default: if (s.t >= s.dur) decide();
        }
        if (tn > s.nextBlink && s.mode !== "sleep") { s.blinkUntil = tn + 0.13; s.nextBlink = tn + 2 + Math.random() * 3.5; }
      }
      const el = ref.current, sp = spriteRef.current;
      if (el) el.style.transform = `translate3d(${s.x - 21}px, ${s.y - FOOT + yOff}px, 0)`;
      if (sp) sp.style.transform = `rotate(${rot}deg) scale(${(s.flip ? -1 : 1) * sx}, ${sy})`;
      // eyes follow the pointer (or look around when nobody is there)
      let lx = 0, ly = 0;
      if (ptr.x >= 0 && s.mode !== "sleep") {
        const dx = ptr.x - s.x, dy = ptr.y - (s.y - 30), d = Math.hypot(dx, dy) || 1;
        lx = (dx / d) * Math.min(1, d / 120) * (s.flip ? -1 : 1); ly = (dy / d) * Math.min(1, d / 120);
      } else if (s.mode === "idle") lx = Math.sin(tn * 0.7);
      const mood = s.hover && s.mode !== "sleep" ? "shy" : s.mood;
      const bubble = tn < s.bubbleUntil ? s.bubble : null, blink = tn < (s.blinkUntil || 0);
      const v = { pose: s.pose, mood, blink, lookX: Math.round(lx * 5) / 5, lookY: Math.round(ly * 5) / 5, bubble };
      if (!lastView || Object.keys(v).some((k) => v[k] !== lastView[k])) { lastView = v; setView(v); }
    }
    raf = requestAnimationFrame(frame);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("ogonek:focus", onFocus); window.removeEventListener("ogonek:release", onRelease);
      window.removeEventListener("pointermove", onPtr); window.removeEventListener("scroll", wake); window.removeEventListener("keydown", wake);
    };
  }, []);

  return (
    <div className="mascot-layer" ref={layerRef}>
      <div className="mascot" ref={ref}>
        {view.bubble && <div className={`mascot-bubble ${st.current?.flip ? "left" : ""}`} role="status">{view.bubble}</div>}
        <button className="mascot-btn" onClick={() => st.current?.onClick()} onPointerEnter={() => st.current?.onHover(true)} onPointerLeave={() => st.current?.onHover(false)}
          aria-label="Огонёк — подсказка по разделу">
          <span className="mascot-sprite" ref={spriteRef}>
            <MascotSprite pose={view.pose} mood={view.mood} blink={view.blink} lookX={view.lookX} lookY={view.lookY} />
          </span>
        </button>
      </div>
    </div>
  );
}
