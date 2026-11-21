export type Vec = [number, number, number];
export type Camera = { yaw: number; pitch: number; zoom: number };
export type Point = { x: number; y: number; z: number };
const TAU = Math.PI * 2;
/** Identity order must stay independent of browser locale. */
export function compareKeys(a: string, b: string): number { return a < b ? -1 : a > b ? 1 : 0; }
export function unit(v: Vec): Vec {
  const size = Math.hypot(...v);
  return size < 1e-10 ? [0, 0, 1] : v.map(x => x / size) as Vec;
}
export function rotate([x, y, z]: Vec, camera: Camera): Vec {
  const a = Math.cos(camera.yaw) * x + Math.sin(camera.yaw) * z;
  const b = -Math.sin(camera.yaw) * x + Math.cos(camera.yaw) * z;
  return [a, Math.cos(camera.pitch) * y - Math.sin(camera.pitch) * b,
    Math.sin(camera.pitch) * y + Math.cos(camera.pitch) * b];
}
export function unrotate([x, y, z]: Vec, camera: Camera): Vec {
  const b = -Math.sin(camera.pitch) * y + Math.cos(camera.pitch) * z;
  return [Math.cos(camera.yaw) * x - Math.sin(camera.yaw) * b,
    Math.cos(camera.pitch) * y + Math.sin(camera.pitch) * z,
    Math.sin(camera.yaw) * x + Math.cos(camera.yaw) * b];
}
export function focus(v: Vec, camera: Camera): Camera {
  return { ...camera, yaw: -Math.atan2(v[0], v[2]), pitch: Math.atan2(v[1], Math.hypot(v[0], v[2])) };
}
export function project(v: Vec, camera: Camera, width: number, height: number, flat = false): Point {
  const radius = Math.min(width, height) * .38 * camera.zoom;
  if (flat) return { x: width / 2 + Math.atan2(v[0], v[2]) / Math.PI * radius,
    y: height / 2 - Math.asin(v[1]) / (Math.PI / 2) * radius, z: 1 };
  const [x, y, z] = rotate(v, camera);
  return { x: width / 2 + x * radius, y: height / 2 - y * radius, z };
}
export function surface(x: number, y: number, camera: Camera, width: number, height: number): Vec {
  const radius = Math.min(width, height) * .38 * camera.zoom;
  const a = (x - width / 2) / radius, b = -(y - height / 2) / radius;
  return unit(unrotate(unit([a, b, Math.sqrt(Math.max(0, 1 - a * a - b * b))]), camera));
}
export function positions(keys: string[], previous: Record<string, Vec>, insertion?: { key: string; point: Vec }): Record<string, Vec> {
  const next = { ...previous };
  const sorted = [...keys].sort(compareKeys);
  const incremental = Object.keys(previous).length > 0;
  sorted.forEach((key, i) => {
    if (next[key]) return;
    const y = 1 - 2 * (i + .5) / sorted.length;
    const phi = i * Math.PI * (3 - Math.sqrt(5));
    let candidate = sorted.length === 1 ? [0, 0, 1] as Vec : unit([Math.cos(phi) * Math.sqrt(1 - y * y), y, Math.sin(phi) * Math.sqrt(1 - y * y)]);
    if (insertion?.key === key) candidate = unit(insertion.point);
    // Only a new node checks collisions, never all pairs in a frame. Retain
    // established positions, with a bounded deterministic local search.
    const others = incremental || insertion?.key === key ? Object.values(next) : [];
    for (let attempt = 0; attempt < 48 && others.some(v => Math.hypot(v[0] - candidate[0], v[1] - candidate[1], v[2] - candidate[2]) < .09); attempt++) {
      candidate = unit([candidate[0] + .11 * Math.cos(attempt * 2.4), candidate[1] + .11 * Math.sin(attempt * 2.4), candidate[2]]);
    }
    next[key] = candidate;
  });
  return next;
}
export function arc(a: Vec, b: Vec, lane = 0, loop = false): Vec[] {
  const dot = Math.max(-1, Math.min(1, a.reduce((sum, x, i) => sum + x * b[i], 0)));
  const helper: Vec = Math.abs(a[1]) < .8 ? [0, 1, 0] : [1, 0, 0];
  const tangent = unit([a[1] * helper[2] - a[2] * helper[1], a[2] * helper[0] - a[0] * helper[2], a[0] * helper[1] - a[1] * helper[0]]);
  if (loop || dot > .99999) return Array.from({ length: 33 }, (_, i) => {
    const t = i / 32 * TAU, scale = .10 + Math.abs(lane) * .04;
    return unit(a.map((x, j) => x + tangent[j] * Math.sin(t) * scale + helper[j] * (1 - Math.cos(t)) * scale) as Vec);
  });
  const angle = Math.acos(dot), sine = Math.sin(angle);
  return Array.from({ length: 25 }, (_, i) => {
    const t = i / 24;
    const v = sine < .0001 ? a.map((x, j) => Math.cos(Math.PI * t) * x + Math.sin(Math.PI * t) * tangent[j]) : a.map((x, j) => (Math.sin((1 - t) * angle) * x + Math.sin(t * angle) * b[j]) / sine);
    return unit(v.map((x, j) => x + lane * .035 * Math.sin(Math.PI * t) * tangent[j]) as Vec);
  });
}
