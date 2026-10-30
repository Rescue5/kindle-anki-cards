/**
 * Plain 2D geometry for light: lamps are placed relative to the element they
 * light, and a beam is the convex hull of the shade's mouth and that element,
 * so the cone always leaves exactly from the shade and lands exactly on the
 * target.
 */

export type Point = { x: number; y: number };
export type Rect = { x: number; y: number; width: number; height: number };

export const add = (a: Point, b: Point): Point => ({ x: a.x + b.x, y: a.y + b.y });
export const sub = (a: Point, b: Point): Point => ({ x: a.x - b.x, y: a.y - b.y });
export const scale = (a: Point, k: number): Point => ({ x: a.x * k, y: a.y * k });
export const length = (a: Point) => Math.hypot(a.x, a.y);
export const normalize = (a: Point): Point => {
  const size = length(a) || 1;
  return { x: a.x / size, y: a.y / size };
};
/** Perpendicular, rotated 90° counter-clockwise in screen coordinates. */
export const perpendicular = (a: Point): Point => ({ x: -a.y, y: a.x });
export const lerp = (a: Point, b: Point, t: number): Point => ({ x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t });

export const corners = (rect: Rect): Point[] => [
  { x: rect.x, y: rect.y },
  { x: rect.x + rect.width, y: rect.y },
  { x: rect.x + rect.width, y: rect.y + rect.height },
  { x: rect.x, y: rect.y + rect.height },
];

export const inflate = (rect: Rect, by: number): Rect => ({ x: rect.x - by, y: rect.y - by, width: rect.width + by * 2, height: rect.height + by * 2 });

export const center = (rect: Rect): Point => ({ x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 });

/** Andrew's monotone chain; returns the hull in counter-clockwise order. */
export function convexHull(points: Point[]): Point[] {
  const sorted = [...points].sort((a, b) => a.x - b.x || a.y - b.y);
  if (sorted.length < 3) return sorted;
  const cross = (o: Point, a: Point, b: Point) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
  const lower: Point[] = [];
  for (const point of sorted) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], point) <= 0) lower.pop();
    lower.push(point);
  }
  const upper: Point[] = [];
  for (const point of [...sorted].reverse()) {
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], point) <= 0) upper.pop();
    upper.push(point);
  }
  return [...lower.slice(0, -1), ...upper.slice(0, -1)];
}

export const toPath = (points: Point[]) =>
  points.length ? `M${points.map((point) => `${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(" L")} Z` : "";

export function pointInPolygon(point: Point, polygon: Point[]): boolean {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const a = polygon[i];
    const b = polygon[j];
    if (a.y > point.y !== b.y > point.y && point.x < ((b.x - a.x) * (point.y - a.y)) / (b.y - a.y) + a.x) inside = !inside;
  }
  return inside;
}

/** The mouth of a shade: a segment centred on `mouth`, perpendicular to the aim. */
export function mouthSegment(mouth: Point, aim: Point, halfWidth: number): [Point, Point] {
  const side = scale(perpendicular(aim), halfWidth);
  return [add(mouth, side), sub(mouth, side)];
}

/** Points on the ellipse that encloses a rectangle: light lands as a soft pool, not a box. */
export function landingEllipse(target: Rect, steps = 28): Point[] {
  const c = center(target);
  const rx = (target.width / 2) * 1.04;
  const ry = (target.height / 2) * 1.16;
  return Array.from({ length: steps }, (_, index) => {
    const angle = (index / steps) * Math.PI * 2;
    return { x: c.x + Math.cos(angle) * rx, y: c.y + Math.sin(angle) * ry };
  });
}

/** The lit cone between a shade's mouth and the pool it lands on. */
export function beamPolygon(mouth: [Point, Point], target: Rect): Point[] {
  return convexHull([...mouth, ...landingEllipse(target)]);
}
