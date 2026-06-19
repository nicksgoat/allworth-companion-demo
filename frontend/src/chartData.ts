// Turns a coarse monthly net-worth series into a dense, organic, daily-style
// curve — so the chart reads like Acorns/Robinhood (hundreds of smooth points)
// instead of 12 jagged ones.
//
// Drawing the raw monthly anchors has two problems:
//   1. Too few points (12) → a coarse, angular line.
//   2. Catmull-Rom smoothing OVERSHOOTS on sharp moves, inventing dips that
//      aren't in the data (the "mountain then cliff" artifact).
//
// We fix both. Fritsch–Carlson monotone-cubic interpolation passes through
// every real month-end value and never overshoots between them. We then
// resample each month into ~14 sub-points and add a subtle, deterministic,
// anchor-pinned wave so the line breathes like real market data without
// changing any real value.

import type { MonthValue } from "./types";

// Small deterministic PRNG (mulberry32) — stable renders, no Math.random jitter
// that would make every frame/screenshot look different.
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Resample monthly anchors into a smooth, organic series.
 * Endpoints are preserved exactly, so any delta computed from the first/last
 * value is unchanged. Each dense point carries the nearest anchor's `month`
 * so scrubbing still shows a sensible label.
 */
export function densify(anchors: MonthValue[], perSegment = 14): MonthValue[] {
  const n = anchors.length;
  if (n < 2) return anchors;
  const y = anchors.map((a) => a.value);

  // Fritsch–Carlson monotone tangents (secant x-spacing is a constant 1).
  const d: number[] = [];
  for (let i = 0; i < n - 1; i++) d.push(y[i + 1] - y[i]);
  const m: number[] = new Array(n);
  m[0] = d[0];
  m[n - 1] = d[n - 2];
  for (let i = 1; i < n - 1; i++) m[i] = (d[i - 1] + d[i]) / 2;
  for (let i = 0; i < n - 1; i++) {
    if (d[i] === 0) {
      m[i] = 0;
      m[i + 1] = 0;
    } else {
      const a = m[i] / d[i];
      const b = m[i + 1] / d[i];
      const s = a * a + b * b;
      if (s > 9) {
        const tau = 3 / Math.sqrt(s);
        m[i] = tau * a * d[i];
        m[i + 1] = tau * b * d[i];
      }
    }
  }

  // Cubic Hermite basis.
  const h00 = (t: number) => 2 * t ** 3 - 3 * t ** 2 + 1;
  const h10 = (t: number) => t ** 3 - 2 * t ** 2 + t;
  const h01 = (t: number) => -2 * t ** 3 + 3 * t ** 2;
  const h11 = (t: number) => t ** 3 - t ** 2;

  const rand = mulberry32(0x5eed);
  // Wave amplitude scales with the range's overall move, floored so even a flat
  // stretch still has a little life. Stays well under 1% of net worth.
  const span = Math.max(Math.abs(y[n - 1] - y[0]), y[0] * 0.02);
  const amp = span * 0.06;

  const out: MonthValue[] = [];
  for (let i = 0; i < n - 1; i++) {
    const f1 = 1 + Math.floor(rand() * 2);
    const f2 = 3 + Math.floor(rand() * 2);
    const p1 = rand() * Math.PI * 2;
    const p2 = rand() * Math.PI * 2;
    for (let k = 0; k < perSegment; k++) {
      const t = k / perSegment;
      const base = h00(t) * y[i] + h10(t) * m[i] + h01(t) * y[i + 1] + h11(t) * m[i + 1];
      const env = 4 * t * (1 - t); // 0 at the anchors, 1 mid-segment → pins the curve
      const wave =
        env * amp * (Math.sin(f1 * Math.PI * t + p1) * 0.6 + Math.sin(f2 * Math.PI * t + p2) * 0.4);
      out.push({ month: anchors[t < 0.5 ? i : i + 1].month, value: base + wave });
    }
  }
  out.push({ month: anchors[n - 1].month, value: y[n - 1] }); // exact final anchor
  return out;
}
