// USM brand: a layered flame — deep red outer tongues, orange and yellow inner flames, a white-hot core.
// Own drawing on the original USM silhouette (main tip leaning right, a tongue on the left), not a copy of any stock flame.
export const FLAME_LAYERS = [
  { cls: "fl-1", d: "M32 79C15 79 3 68 3 53c0-8 3-13 5.5-17 0 5 2 8 5 9-2-8-3.5-16-.5-24 3 7 6.5 11 9.5 12C22 22 28 10 40 2c-2 10 2 17 7 22 2-3 4.5-6 8-9 0 6 1 11 3 15 3 6 4 13 3 20C59.5 67 49 79 32 79z", from: "#c8261a", to: "#ff6a1a" },
  { cls: "fl-2", d: "M32 77C19 77 9 68 9 56c0-7 3-11 6-15 0 5 2 8 5 9-1-9 3-19 13-28 0 9 4 14 9 18 2-3 4-6 7-9 2 6 6 13 6 22 0 13-9 24-23 24z", from: "#ff7a1c", to: "#ffb02e" },
  { cls: "fl-3", d: "M32 76c-9 0-16-7-16-16 0-7 4-12 8-16 0 5 2 8 5 9-1-7 2-13 8-19 0 7 3 12 7 16 2-3 3-5 4-7 2 5 3 10 3 15 0 11-8 18-19 18z", from: "#ffb62e", to: "#ffe169" },
  { cls: "fl-4", d: "M32 76c-6 0-10-5-10-11 0-5 3-9 7-13 0 5 2 7 4 8 0-5 2-9 5-12 2 6 5 10 5 16 0 7-5 12-11 12z", from: "#fff6c8", to: "#fffdf2" },
];

function Flame({ id }) {
  return (
    <>
      <defs>
        {FLAME_LAYERS.map((l, i) => (
          <linearGradient key={i} id={`${id}-${i}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor={l.from} /><stop offset="1" stopColor={l.to} />
          </linearGradient>
        ))}
      </defs>
      {FLAME_LAYERS.map((l, i) => <path key={i} className={`fl ${l.cls}`} d={l.d} fill={`url(#${id}-${i})`} />)}
    </>
  );
}

export function Logo({ size = 28, word = true }) {
  return (
    <span className="logo">
      <svg className="logo-flame" width={size} height={size * 1.25} viewBox="0 0 64 80" aria-hidden="true"><Flame id="lg" /></svg>
      {word && <span className="logo-word">USM</span>}
    </span>
  );
}

/* Mascot drawing. Body = the logo flame; arms and legs are animated in CSS, the face changes with the mood. */
export function MascotSprite({ pose = "idle", mood = "smile", blink = false, lookX = 0, lookY = 0 }) {
  const eyes = blink || mood === "sleep";
  const ex = lookX * 2.2, ey = lookY * 1.6;
  return (
    <svg className={`og og-${pose} og-m-${mood}`} viewBox="-4 -2 72 94" width="42" height="58" aria-hidden="true">
      <g className="og-legs">
        <path className="og-leg og-leg-l" d="M25 76v9" />
        <path className="og-leg og-leg-r" d="M39 76v9" />
      </g>
      <g className="og-arm og-arm-l"><path d="M9 57q-6 2-8 7" /></g>
      <g className="og-arm og-arm-r"><path d="M55 57q6 2 8 7" /></g>
      <g className="og-body">
        <Flame id="og" />
        <g className="og-face" transform={`translate(${ex} ${ey})`}>
          {eyes ? (
            <>
              <path d="M20 53q4.5 3 9 0" className="og-lid" /><path d="M35 53q4.5 3 9 0" className="og-lid" />
            </>
          ) : (
            <>
              <ellipse cx="24.5" cy="51.5" rx="5.4" ry="6.2" fill="#fff" stroke="#b8361a" strokeOpacity=".55" strokeWidth=".8" />
              <ellipse cx="39.5" cy="51.5" rx="5.4" ry="6.2" fill="#fff" stroke="#b8361a" strokeOpacity=".55" strokeWidth=".8" />
              <circle cx={25 + lookX * 1.4} cy={52.5 + lookY} r="3.3" fill="#2a1208" /><circle cx={40 + lookX * 1.4} cy={52.5 + lookY} r="3.3" fill="#2a1208" />
              <circle cx={26.3 + lookX * 1.4} cy={51 + lookY} r="1.2" fill="#fff" /><circle cx={41.3 + lookX * 1.4} cy={51 + lookY} r="1.2" fill="#fff" />
              <circle cx={24 + lookX * 1.4} cy={54.2 + lookY} r=".55" fill="#fff" opacity=".8" /><circle cx={39 + lookX * 1.4} cy={54.2 + lookY} r=".55" fill="#fff" opacity=".8" />
            </>
          )}
          <ellipse cx="17.5" cy="60" rx="3.6" ry="2.1" fill="#ff4d6d" opacity={mood === "love" || mood === "shy" ? 0.8 : 0.45} />
          <ellipse cx="46.5" cy="60" rx="3.6" ry="2.1" fill="#ff4d6d" opacity={mood === "love" || mood === "shy" ? 0.8 : 0.45} />
          {mood === "happy" || mood === "love" ? <path d="M27.5 60.5q4.5 6 9 0z" fill="#5a1606" stroke="#2a1208" strokeWidth="1.2" strokeLinejoin="round" />
            : mood === "wow" ? <ellipse cx="32" cy="62" rx="2.4" ry="3" fill="#5a1606" stroke="#2a1208" strokeWidth="1.1" />
            : mood === "sleep" ? <ellipse cx="32" cy="62" rx="1.6" ry="1.2" fill="#5a1606" />
            : <path d="M28.5 61q3.5 3.4 7 0" fill="none" stroke="#2a1208" strokeWidth="1.8" strokeLinecap="round" />}
        </g>
      </g>
    </svg>
  );
}
