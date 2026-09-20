/**
 * The one piece of geometry the Ocean Research Hub identity is built from:
 * a fixed relief field sampled into closed isobaths. The brand mark is a crop
 * of the same field the landing hero draws at full size.
 *
 * Deterministic on purpose — no randomness, so server and client markup match.
 */
export type ContourOptions = {
  cx: number;
  cy: number;
  level: number;
  /** Which isobath this is; shifts the relief and drifts the summit. */
  index: number;
  samples?: number;
  /** Vertical squash, so the field reads as a map rather than a target. */
  flatten?: number;
  /** Per-level drift of the summit, in user units. */
  drift?: number;
  precision?: number;
  /** Fit a closed spline through the samples instead of joining them with lines. */
  smooth?: boolean;
};

export function contourPath({
  cx,
  cy,
  level,
  index,
  samples = 72,
  flatten = 0.86,
  drift = 0,
  precision = 1,
  smooth = false,
}: ContourOptions): string {
  const points: [number, number][] = [];
  for (let step = 0; step < samples; step += 1) {
    const t = (step / samples) * Math.PI * 2;
    const relief = 1 + 0.17 * Math.sin(3 * t + index * 0.55) + 0.09 * Math.cos(5 * t - index * 0.8);
    const r = level * relief;
    points.push([
      cx + r * Math.cos(t) * 1.02 + index * drift,
      cy + r * Math.sin(t) * flatten - index * drift * 0.75,
    ]);
  }
  const round = (n: number) => n.toFixed(precision);
  if (!smooth) {
    return `M${points.map(([x, y]) => `${round(x)} ${round(y)}`).join("L")}Z`;
  }

  // Closed Catmull-Rom spline, converted to cubic Béziers: few samples, no
  // corners. Small marks need this; the full-size field has enough points not to.
  const at = (i: number) => points[(i + points.length) % points.length];
  let d = `M${round(points[0][0])} ${round(points[0][1])}`;
  for (let i = 0; i < points.length; i += 1) {
    const [x0, y0] = at(i - 1);
    const [x1, y1] = at(i);
    const [x2, y2] = at(i + 1);
    const [x3, y3] = at(i + 2);
    d +=
      `C${round(x1 + (x2 - x0) / 6)} ${round(y1 + (y2 - y0) / 6)}` +
      `,${round(x2 - (x3 - x1) / 6)} ${round(y2 - (y3 - y1) / 6)}` +
      `,${round(x2)} ${round(y2)}`;
  }
  return `${d}Z`;
}
