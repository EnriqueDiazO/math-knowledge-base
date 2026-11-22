import type { Data, View } from "./model";
import { studyTheme } from "./theme";
import { unit } from "./geometry";
import type { Vec } from "./geometry";
export function areaColor(name: string): string {
  let hash = 0;
  for (const char of name) hash = (hash * 31 + char.codePointAt(0)!) >>> 0;
  return [studyTheme.turquoise, studyTheme.sky, studyTheme.amber][hash % 3];
}
export function regions(
  data: Data,
  view: View,
): {
  name: string;
  color: string;
  center: Vec;
  outline: Vec[];
  petals: Vec[][];
}[] {
  return (view.areas ?? []).flatMap((name) => {
    const members = data.nodes.filter(
      (n) => n.categorias.includes(name) && view.points[n.key],
    );
    if (!members.length) return [];
    const center = unit(
      members.reduce<Vec>(
        (sum, n) => sum.map((v, i) => v + view.points[n.key][i]) as Vec,
        [0, 0, 0],
      ),
    );
    const axis: Vec = Math.abs(center[1]) < 0.8 ? [0, 1, 0] : [1, 0, 0],
      a = unit([
        center[1] * axis[2] - center[2] * axis[1],
        center[2] * axis[0] - center[0] * axis[2],
        center[0] * axis[1] - center[1] * axis[0],
      ]),
      b = unit([
        center[1] * a[2] - center[2] * a[1],
        center[2] * a[0] - center[0] * a[2],
        center[0] * a[1] - center[1] * a[0],
      ]);
    const ring = (scale: number, petal = false) =>
      Array.from({ length: 65 }, (_, i) => {
        const angle = (i / 64) * Math.PI * 2,
          r = scale * (petal ? 0.78 + 0.22 * Math.cos(angle * 6) : 1);
        return unit(
          center.map(
            (v, j) =>
              v +
              Math.tan(r) * (a[j] * Math.cos(angle) + b[j] * Math.sin(angle)),
          ) as Vec,
        );
      });
    return [
      {
        name,
        color: areaColor(name),
        center,
        outline: ring(0.65),
        petals: view.mandala ? [ring(0.47, true), ring(0.28, true)] : [],
      },
    ];
  });
}
