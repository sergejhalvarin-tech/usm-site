// USM kiln — physical model of one batch (2 retorts), integrated numerically once and then played back.
//
//  • Charge heating: the wood pile is split into N concentric layers; the shell heats the outer one,
//        heat moves inwards by conduction + radiation through the pile, k_eff = k₀ + 4σεd·T³ —
//        so drying and pyrolysis run as a front from the wall to the core:  Cⱼ·dTⱼ/dt = Σq − ṁ_evap·r − Σ ΔHᵢ·ṁᵢ
//  • Drying: free water boils at ~100 °C, bound water pushes the plateau higher (rate ∝ (T − 95)·√(w/w₀))
//  • Pyrolysis: three independent first-order reactions (hemicellulose, cellulose, lignin)
//        dmᵢ/dt = −Aᵢ·exp(−Eᵢ / R·T)·mᵢ  →  char + tar + gas + reaction water (component yields)
//  • Afterburning: gas + tar burn under the retorts; air is set by the PLC from the O₂ set-point,
//        λ = 21 / (21 − O₂), air = λ·Σ AFRᵢ·ṁᵢ,  limited by the fan; excess gas is flared at the vent («свеча»)
//  • Zone temperature from the steady energy balance of the combustion space
//  • Gas dynamics: pressure in the retort = pressure loss in pipe ТП200 (Ø159×6), Δp = ΣK·ρv²/2, ρ = pM/RT
//  • Chimney draft: Δp = g·H·(ρ_air − ρ_flue), H = 7,2 m;  fan affinity laws Q ∝ n, P ∝ n³
//  • Calcination raises fixed carbon with the highest treatment temperature; fixed carbon mass is conserved
//  • Cooling with dampers closed: Newton's law, τ = C / UA
// Values are typical for retort carbonisation of birch at 25 % moisture; they are a model, not a guarantee.

const R = 8.314, G = 9.81, TA = 20, P0 = 101325, r = 2257;               // kJ/kg latent heat
const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
export const smooth = (a, b, x) => { const t = clamp((x - a) / (b - a)); return t * t * (3 - 2 * t); };

/* ---- charge (one retort) */
export const CHARGE = { stacked: 5.2, dry: 2030, moisture: 0.25, steel: 1150 };   // m³, kg dry wood, wet basis, kg steel
const W0 = CHARGE.dry * CHARGE.moisture / (1 - CHARGE.moisture);                   // kg water
/* biomass components: share, Arrhenius A [1/s], E [J/mol], product yields, reaction heat ΔH [kJ/kg] (− = exothermic) */
export const COMP = [
  { id: "hemi", name: "Гемицеллюлозы", x: 0.32, A: 7.3e6, E: 105e3, char: 0.30, tar: 0.28, dH: -220 },
  { id: "cell", name: "Целлюлоза", x: 0.44, A: 8.6e13, E: 195e3, char: 0.20, tar: 0.58, dH: 120 },
  { id: "lign", name: "Лигнин", x: 0.24, A: 9.0, E: 55e3, char: 0.48, tar: 0.22, dH: -320 },
];
const RW = 0.12;                                   // reaction water, share of decomposed mass
/* fuels: lower heating value [kJ/kg], stoichiometric air [kg/kg] */
const LHV = { gas: 9000, tar: 20000, wood: 15000 }, AFR = { gas: 2.6, tar: 6.4, wood: 5.0 };
/* plant */
const UA = 0.16, UA_LOSS = 0.09, UA_COOL = 0.11;   // kW/K: zone→retort (each), zone→ambient, retort→ambient when shut
const FB_MAX = 380;                                 // kW, startup firebox
const FAN = { Qmax: 0.5, P: 0.74, minHz: 15 };      // m³/s at 50 Hz (~1800 m³/h); shaft kW at 50 Hz: Q·Δp/η, Δp ≈ 0.9 kPa in DN200 + nozzles, η 0.6 (motor 1.5 kW)
const O2_SET = 6, T_ZONE_MAX = 950, CP = 1.2;       // %, °C, kJ/kgK flue
const PIPE = { D: 0.147, K: 6.8 }, CHIMNEY_H = 7.2;
const T_CALC = 540, CALC_HOLD = 3600, T_UNLOAD = 150;
const fixedCarbon = (htt) => Math.max(20, 95 - 75 * Math.exp(-(htt - 200) / 140));   // % at the highest treatment temperature

const N = 6;                                                    // layers of the wood pile, outer → core
const RET_R = 0.85, RET_L = 2.68, SIGMA = 5.67e-11;               // m, m, kW/m²K⁴
/* conductance between layers j and j+1 [kW/K]: k_eff·A/Δr, k_eff = k₀ + 4σεd·T³ (radiation across the gaps) */
const condG = (j, Tm) => {
  const rr = RET_R * (1 - (j + 1) / N), A = 2 * Math.PI * Math.max(rr, 0.08) * RET_L, dr = RET_R / N;
  const k = K0 + 4 * SIGMA * 0.85 * GAP * (Tm + 273.15) ** 3;
  return (k * A) / dr;
};
const K0 = 0.0035, GAP = 0.12;                                    // kW/mK (wood pile), m (mean gap between logs)

function simulate() {
  const dt = 10, out = [], f = 1 / N, w0 = W0 * f;
  const L = Array.from({ length: N }, () => ({ T: TA, w: w0, m: COMP.map((c) => CHARGE.dry * c.x * f), char: 0 }));
  let tar = 0, gas = 0, rwat = 0, htt = TA, char = 0;
  let t = 0, candle = true, mode = "heat", holdT = 0, peakGas = 1e-6, peakSteam = 1e-6, peakFlue = 1e-6, Tz = TA;
  const ev = {};
  for (let step = 0; step < 300000; step++) {
    /* reactions and drying per layer */
    let dChar = 0, dTar = 0, dGas = 0, dRw = 0, evap = 0;
    const qR = new Array(N).fill(0), evL = new Array(N).fill(0), dmL = [];
    L.forEach((l, j) => {
      const TK = l.T + 273.15;
      const dm = l.m.map((mi, i) => mi * (1 - Math.exp(-COMP[i].A * Math.exp(-COMP[i].E / (R * TK)) * dt)));
      dm.forEach((d, i) => { const c = COMP[i]; dChar += d * c.char; l.char += d * c.char; dTar += d * c.tar; dRw += d * RW; dGas += d * (1 - c.char - c.tar - RW); qR[j] += d * c.dH; });
      dmL.push(dm);
      evL[j] = l.w > 0 ? Math.min(l.w, 0.0047 * f * Math.max(0, l.T - 95) * Math.sqrt(l.w / w0) * dt) : 0;
      evap += evL[j];
    });
    const dmSum = dmL.flat().reduce((a, b) => a + b, 0);
    const wTot = L.reduce((a, l) => a + l.w, 0), mTot = L.reduce((a, l) => a + l.m.reduce((x, y) => x + y, 0), 0);
    const Tavg = L.reduce((a, l) => a + l.T, 0) / N, Twall = L[0].T, Tcore = L[N - 1].T;
    const rate = { tar: dTar / dt, gas: dGas / dt, water: (evap + dRw) / dt, total: (dTar + dGas + evap + dRw) / dt };
    const steamFrac = rate.water / Math.max(rate.total, 1e-9);
    /* PLC: candle closes when the gas is combustible (little water vapour, flame detected) — latched */
    if (candle && Twall > 230 && steamFrac < 0.45 && rate.gas > 2e-4) { candle = false; ev.candle = t; }
    if (Tavg >= 100 && ev.boil == null) ev.boil = t;
    if (wTot < 0.02 * W0 && ev.dry == null) ev.dry = t;
    if (Tavg >= 280 && ev.t280 == null) ev.t280 = t;
    const woodLeft = mTot / CHARGE.dry;
    if (mode === "heat" && !candle && woodLeft < 0.04) { mode = "calc"; ev.pyroEnd = t; }
    if (mode === "calc" && Tcore >= T_CALC - 40) { holdT += dt; if (holdT >= CALC_HOLD) { mode = "cool"; ev.cool = t; } }

    /* combustion space (both retorts feed it) */
    let fuelGas = 0, fuelTar = 0, vented = 0, Qfb = 0, air = 0, lambda = 0, Qcomb = 0, mFlue = 0, inert = 0, fanHz = 0;
    if (mode !== "cool") {
      let gasIn = 0, tarIn = 0;
      if (!candle) { gasIn = 2 * rate.gas; tarIn = 2 * rate.tar; inert = 2 * rate.water; }
      const Qvol0 = gasIn * LHV.gas + tarIn * LHV.tar;
      // firebox: full during start-up and drying, then the PLC trims it as the gas takes over; tops up for calcination
      if (mode === "calc") Qfb = FB_MAX * clamp(1 - Qvol0 / 450) * (Tcore < T_CALC - 40 ? 1 : 0.35);
      else Qfb = candle ? FB_MAX : FB_MAX * clamp(1 - Qvol0 / 380);
      const fbFuel = Qfb / LHV.wood, airMax = FAN.Qmax * 1.2;
      const zone = (keep) => {
        const fg = gasIn * keep, ft = tarIn * keep, st = AFR.gas * fg + AFR.tar * ft + AFR.wood * fbFuel;
        const Q = fg * LHV.gas + ft * LHV.tar + Qfb;
        const tz = (a) => { const mf = a + fg + ft + fbFuel + inert; return { mf, Tz: (Q + mf * CP * TA + 2 * UA * Twall + UA_LOSS * TA) / (mf * CP + 2 * UA + UA_LOSS) }; };
        let a = Math.min((21 / (21 - O2_SET)) * st, airMax), z = tz(a);
        if (z.Tz > T_ZONE_MAX && st > 0) {                          // dilute with more air to protect the steel
          const need = (Q - 2 * UA * (T_ZONE_MAX - Twall) - UA_LOSS * (T_ZONE_MAX - TA)) / (CP * (T_ZONE_MAX - TA));
          a = clamp(need - fg - ft - fbFuel - inert, a, airMax); z = tz(a);
        }
        return { fg, ft, st, Q, a, ...z };
      };
      // keep the burner lean (λ ≥ 1.15) and the zone ≤ T_ZONE_MAX; whatever the fan cannot burn is flared at the vent
      let lo = 0, hi = 1, z = zone(1);
      if (z.st * 1.15 > airMax + 1e-9 || z.Tz > T_ZONE_MAX + 1) {
        for (let it = 0; it < 22; it++) { const mid = (lo + hi) / 2, zm = zone(mid); if (zm.st * 1.15 <= airMax && zm.Tz <= T_ZONE_MAX + 1) lo = mid; else hi = mid; }
        z = zone(lo);
      }
      fuelGas = z.fg; fuelTar = z.ft; vented = gasIn + tarIn - fuelGas - fuelTar;
      Qcomb = z.Q; air = z.a; mFlue = z.mf; Tz = z.Tz; lambda = z.st > 0 ? air / z.st : 0;
      fanHz = air > 0 ? clamp((50 * air) / 1.2 / FAN.Qmax, FAN.minHz, 50) : 0;
    } else {
      Tz += (Twall - Tz) * 0.02;                                     // closed kiln follows the retorts
    }
    /* energy balance per layer: shell → outer layer, conduction inwards */
    const qIn = mode === "cool" ? -UA_COOL * (Twall - TA) : UA * (Tz - Twall);
    const flux = L.slice(0, N - 1).map((l, j) => condG(j, (l.T + L[j + 1].T) / 2) * (l.T - L[j + 1].T));
    L.forEach((l, j) => {
      const mW = l.m.reduce((a, b) => a + b, 0);
      const C = mW * (1.1 + 0.0037 * l.T) + l.w * 4.19 + l.char * (0.85 + 0.0012 * l.T) + (j === 0 ? CHARGE.steel * 0.5 : 0);
      const q = (j === 0 ? qIn : flux[j - 1]) - (j < N - 1 ? flux[j] : 0);
      l.T += (q * dt - evL[j] * r - qR[j]) / C;
      l.w -= evL[j]; l.m = l.m.map((mi, i) => mi - dmL[j][i]);
    });
    char += dChar; tar += dTar; gas += dGas; rwat += dRw;
    const T = L.reduce((a, l) => a + l.T, 0) / N; htt = Math.max(htt, Math.min(T, L[N - 1].T + 30));

    /* gas dynamics */
    const nDot = rate.water / 0.018 + rate.gas / 0.03 + rate.tar / 0.1;              // mol/s leaving one retort
    const Qv = (nDot * R * (T + 273.15)) / P0;                                        // m³/s
    const A = Math.PI * PIPE.D ** 2 / 4, v = Qv / A, rho = Qv > 0 ? rate.total / Qv : 0;
    const dp = PIPE.K * rho * v * v / 2;
    const Tch = mode === "cool" ? TA : TA + 0.42 * (Tz - TA);
    const draft = mode === "cool" ? 0 : G * CHIMNEY_H * (353 / (TA + 273) - 355 / (Tch + 273));
    const steamOut = candle ? 2 * rate.total : vented;
    peakGas = Math.max(peakGas, fuelGas + fuelTar); peakSteam = Math.max(peakSteam, steamOut); peakFlue = Math.max(peakFlue, mFlue);
    const cfix = fixedCarbon(htt), charEff = char * (72 / Math.max(72, cfix));

    if (step % 6 === 0) out.push({
      t, T, Twall, Tcore: L[N - 1].T, layers: L.map((l) => l.T), lw: L.map((l) => l.m.reduce((x, y) => x + y, 0) / (CHARGE.dry * f)), lwat: L.map((l) => l.w / w0), Tz, mode, candle, w: wTot, woodLeft,
      comp: COMP.map((c, i) => L.reduce((a, l) => a + l.m[i], 0) / (CHARGE.dry * c.x)),
      dmdt: (dmSum / dt) * 2 * 3600, steamKgH: steamOut * 3600, fuelKgH: (fuelGas + fuelTar) * 3600, ventKgH: vented * 3600,
      Qcomb, Qfb, qRetort: mode === "cool" ? 0 : qIn, lambda, o2: mode === "cool" ? 20.9 : lambda > 0 ? 21 * (lambda - 1) / lambda : 20.9,
      air, fanHz, fanKW: FAN.P * (fanHz / 50) ** 3, mFlue, Tch, draft, dp, v, cfix,
      charKg: 2 * charEff, tarKg: 2 * tar, gasKg: 2 * gas, waterKg: 2 * (W0 - wTot + rwat),
      mass: (mTot + wTot + charEff) / (CHARGE.dry + W0),
      fuelRaw: fuelGas + fuelTar, steamRaw: steamOut, flueRaw: mFlue, fbRaw: Qfb / FB_MAX,
    });
    t += dt;
    if (mode === "cool" && L[N - 1].T <= T_UNLOAD) { ev.end = t; break; }
  }
  for (const s of out) { s.gas = s.fuelRaw / peakGas; s.steam = s.steamRaw / peakSteam; s.flue = s.flueRaw / peakFlue; s.fire = s.fbRaw; }
  return { out, ev, total: ev.end };
}

const SIM = simulate();
export const CYCLE_HOURS = SIM.total / 3600;
const frac = (t) => t / SIM.total;
const e = SIM.ev, torrEnd = Math.max(e.t280, e.candle + 600);

export const PHASES = [
  { id: "ignite", from: 0, to: frac(e.boil), name: "Розжиг", range: "20 → 100 °C",
    formula: "C·dT/dt = UA·(T_зоны − T)", note: "Горит растопочная топка. Тепло идёт к стаканам через зону под ними; чем больше разница температур, тем быстрее греется закладка." },
  { id: "dry", from: frac(e.boil), to: frac(e.candle), name: "Сушка", range: "100–230 °C",
    formula: "ṁ_исп = Q / r,  r = 2,26 МДж/кг", note: "Сушка идёт фронтом от стенки к центру: пока во внутренних слоях есть вода, они стоят на «полке» около 100 °C. Пар уходит через открытую свечу — в зону горения его не пускают." },
  { id: "torr", from: frac(e.candle), to: frac(torrEnd), name: "Термолиз", range: "230–280 °C",
    formula: "k = A·e^(−Eₐ/RT),  Eₐ(гемиц.) ≈ 105 кДж/моль", note: "У стенки уже разлагаются гемицеллюлозы (реакция экзотермична), а в центре ещё идёт сушка. Пара в газе стало меньше 45 %, датчик видит пламя — ПЛК закрыл свечу и пустил газ на дожиг." },
  { id: "pyro", from: frac(torrEnd), to: frac(e.pyroEnd), name: "Пиролиз", range: "280–450 °C",
    formula: "λ = 21 / (21 − O₂),  Q = Σ ṁᵢ·LHVᵢ", note: "Целлюлоза и лигнин дают газ и смолы, они сгорают под стаканами — печь греет себя сама, топка гаснет. Воздух по O₂ = 6 %; если зона перегревается выше 950 °C, ПЛК разбавляет воздухом, а что вентилятор не сожжёт — сбрасывает на свечу." },
  { id: "calc", from: frac(e.pyroEnd), to: frac(e.cool), name: "Прокалка", range: `450–${T_CALC} °C`,
    formula: "C_fix = f(T_max),  m_C = const", note: "Летучие почти вышли. Уголь держат выше 500 °C — связанный углерод растёт, масса угля немного падает: уходят остаточные летучие." },
  { id: "cool", from: frac(e.cool), to: 1, name: "Остывание", range: `${T_CALC} → ${T_UNLOAD} °C`,
    formula: "T(t) = T₀ + (T₁ − T₀)·e^(−t/τ),  τ = C / UA", note: "Вентилятор и топка остановлены, шиберы и свеча закрыты — воздуха к углю нет. Ниже 150 °C реторту выкатывают в камеру охлаждения." },
];
export const phaseAt = (p) => PHASES.find((ph) => p >= ph.from && p < ph.to) || PHASES[PHASES.length - 1];

export function state(p) {
  const n = SIM.out.length, x = clamp(p, 0, 1) * (n - 1), i = Math.floor(x), f = x - i;
  const a = SIM.out[i], b = SIM.out[Math.min(n - 1, i + 1)], o = { ...a };
  for (const key of ["T", "Twall", "Tcore", "Tz", "air", "mFlue", "mass", "cfix", "Qcomb", "Qfb", "qRetort", "o2", "fanHz", "fanKW", "dp", "v", "draft", "Tch", "dmdt", "steamKgH", "fuelKgH", "ventKgH", "lambda", "charKg", "gas", "steam", "flue", "fire", "w", "woodLeft"])
    o[key] = a[key] + (b[key] - a[key]) * f;
  o.comp = a.comp.map((c, j) => c + (b.comp[j] - c) * f);
  o.layers = a.layers.map((c, j) => c + (b.layers[j] - c) * f);
  o.lw = a.lw.map((c, j) => c + (b.lw[j] - c) * f);
  o.lwat = a.lwat.map((c, j) => c + (b.lwat[j] - c) * f);
  o.hours = (p * SIM.total) / 3600;
  o.moisture = (100 * o.w) / (o.w + o.woodLeft * CHARGE.dry + o.charKg / 2 + 1e-9);
  o.char = smooth(0.15, 0.9, 1 - o.woodLeft);
  o.glow = clamp((o.T - 300) / 300);
  o.candleOpen = a.candle && a.mode !== "cool";
  o.airDamper = o.fanHz > 0 ? Math.round(o.fanHz > FAN.minHz + 0.1 ? 100 : clamp((o.air / 1.2) / (FAN.Qmax * FAN.minHz / 50)) * 100) : 0;
  o.chimneyDamper = a.mode === "cool" ? 0 : Math.round(25 + 75 * clamp(o.mFlue / 0.9));
  return o;
}

export const SERIES = SIM.out.map((s, i) => ({ p: i / (SIM.out.length - 1), T: s.T, Twall: s.Twall, Tcore: s.Tcore, Tz: s.Tz, rate: s.dmdt }));
export const LAYERS = N;
export const SUMMARY = (() => { const last = SIM.out[SIM.out.length - 1]; return { hours: CYCLE_HOURS, charKg: last.charKg, cfix: last.cfix, dry: CHARGE.dry * 2 }; })();
export const temperature = (p) => state(p).T;
