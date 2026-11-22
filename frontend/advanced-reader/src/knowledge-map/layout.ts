import { unit, unrotate } from "./geometry";
import type { Vec, Camera } from "./geometry";
import type { View, Data } from "./model";
export function dragSurface(
  x: number,
  y: number,
  camera: Camera,
  width: number,
  height: number,
  side: number,
): Vec {
  const radius = Math.min(width, height) * 0.36 * camera.zoom;
  let a = (x - width / 2) / radius,
    b = -(y - height / 2) / radius;
  const length = Math.hypot(a, b);
  if (length > 0.995) {
    a *= 0.995 / length;
    b *= 0.995 / length;
  }
  return unit(
    unrotate([a, b, Math.sqrt(Math.max(0, 1 - a * a - b * b)) * side], camera),
  );
}
export function relocate(view: View, key: string, point: Vec): void {
  view.points[key] = unit(point);
  view.layoutDirty = true;
}
export function thematicLayout(data: Data, view: View): Record<string, Vec> {
  const next = { ...view.points },
    areas = view.areas ?? [],
    pinned = new Set(view.pinned ?? []);
  const groups = new Map<string, string[]>();
  data.nodes.forEach((node) => {
    if (pinned.has(node.key)) return;
    const area = areas.find((a) => node.categorias.includes(a)) ?? "";
    groups.set(area, [...(groups.get(area) ?? []), node.key]);
  });
  [...groups.entries()].forEach(([area, keys], index) => {
    const phi = (index + 0.5) * 2.3999632297,
      center = unit([Math.cos(phi), area ? 0.35 : -0.65, Math.sin(phi)]);
    keys.forEach((key, i) => {
      const angle = i * 2.3999632297,
        spread = 0.12 * Math.sqrt(i + 1);
      next[key] = unit([
        center[0] + spread * Math.cos(angle),
        center[1] + spread * Math.sin(angle),
        center[2],
      ]);
    });
  });
  return next;
}
/** Bounded experiment: repel only near points from spatial buckets, no physics. */
export function relax(
  points: Record<string, Vec>,
  pinned: string[],
  iterations = 12,
): Record<string, Vec> {
  const fixed = new Set(pinned);
  let next = structuredClone(points);
  for (let step = 0; step < iterations; step++) {
    const buckets = new Map<string, string[]>();
    const cell = (v: number) => Math.floor((v + 1) * 8);
    Object.entries(next).forEach(([key, p]) => {
      const id = [...p.map(cell)].join(",");
      buckets.set(id, [...(buckets.get(id) ?? []), key]);
    });
    const result = { ...next };
    Object.entries(next).forEach(([key, p]) => {
      if (fixed.has(key)) return;
      const force: Vec = [0, 0, 0],
        base = p.map(cell);
      for (let x = -1; x <= 1; x++)
        for (let y = -1; y <= 1; y++)
          for (let z = -1; z <= 1; z++)
            for (const other of buckets.get(
              [base[0] + x, base[1] + y, base[2] + z].join(","),
            ) ?? []) {
              if (other === key) continue;
              const q = next[other],
                d = Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]);
              if (d > 0 && d < 0.13)
                for (let a = 0; a < 3; a++)
                  force[a] += ((p[a] - q[a]) * 0.12 * (0.13 - d)) / d;
            }
      result[key] = unit([p[0] + force[0], p[1] + force[1], p[2] + force[2]]);
    });
    next = result;
  }
  return next;
}
