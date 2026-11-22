import { describe, expect, it } from "vitest";
import {
  dragSurface,
  relax,
  relocate,
  thematicLayout,
} from "../src/knowledge-map/layout";
import { areaColor, regions } from "../src/knowledge-map/areas";
import {
  contrast,
  applyStudyTheme,
  studyTheme,
} from "../src/knowledge-map/theme";
import {
  freshView,
  useSavedView,
  studyState,
  visibleNodes,
} from "../src/knowledge-map/model";
import type { Data } from "../src/knowledge-map/model";
import type { Vec } from "../src/knowledge-map/geometry";
const data: Data = {
  scope: "test",
  nodes: [
    {
      key: "same@A",
      id: "same",
      source: "A",
      titulo: "Igual",
      tipo: "nota",
      contenido_latex: "$x$",
      comentario: "",
      categorias: ["Análisis", "Geometría"],
      revision: "a",
    },
    {
      key: "same@B",
      id: "same",
      source: "B",
      titulo: "Igual",
      tipo: "teorema",
      contenido_latex: "$y$",
      comentario: "",
      categorias: ["Geometría"],
      revision: "b",
    },
    {
      key: "unclassified@A",
      id: "unclassified",
      source: "A",
      titulo: "Sin área",
      tipo: "nota",
      contenido_latex: "Texto",
      comentario: "",
      categorias: [],
      revision: "c",
    },
  ],
  edges: [],
  sources: [],
  concept_types: [],
  relation_types: [],
};
describe("view-only geometry and real areas", () => {
  it.each([1, -1])(
    "locks the dragged hemisphere and clamps the limb: %i",
    (side) => {
      for (const [x, y] of [
        [300, 250],
        [0, 0],
        [10000, -10000],
      ]) {
        const point = dragSurface(
          x,
          y,
          { yaw: 0, pitch: 0, zoom: 1 },
          600,
          500,
          side,
        );
        expect(Math.hypot(...point)).toBeCloseTo(1);
        expect(Math.sign(point[2])).toBe(side);
      }
    },
  );
  it("reorganizes only by explicitly chosen categories and preserves pinned identities", () => {
    const view = freshView();
    view.points = {
      "same@A": [0, 0, 1],
      "same@B": [1, 0, 0],
      "unclassified@A": [0, -1, 0],
    };
    view.pinned = ["same@A"];
    view.areas = ["Geometría"];
    const before = structuredClone(data),
      points = thematicLayout(data, view);
    expect(points["same@A"]).toEqual(view.points["same@A"]);
    expect(points["same@B"]).not.toEqual(view.points["same@B"]);
    expect(Object.keys(points)).toHaveLength(3);
    Object.values(points).forEach((p) =>
      expect(Math.hypot(...p)).toBeCloseTo(1),
    );
    expect(data).toEqual(before);
    expect(regions(data, view)).toHaveLength(1);
    expect(areaColor("Geometría")).toBe(areaColor("Geometría"));
    view.areas = [];
    expect(regions(data, view)).toEqual([]);
    expect(visibleNodes(data, view)).toHaveLength(3);
  });
  it("settles a bounded relaxation without moving pinned nodes or mutating its input", () => {
    const points: Record<string, Vec> = {
      fixed: [0, 0, 1],
      near: [0.01, 0, Math.sqrt(1 - 0.0001)],
      far: [1, 0, 0],
    };
    const before = structuredClone(points),
      after = relax(points, ["fixed"]);
    expect(points).toEqual(before);
    expect(after.fixed).toEqual(before.fixed);
    expect(after.far).toEqual(before.far);
    expect(
      Math.hypot(
        after.near[0] - after.fixed[0],
        after.near[1] - after.fixed[1],
        after.near[2] - after.fixed[2],
      ),
    ).toBeGreaterThan(0.01);
    Object.values(after).forEach((p) =>
      expect(Math.hypot(...p)).toBeCloseTo(1),
    );
  });
  it("restores independent saved views and never aliases server snapshots", () => {
    const view = freshView();
    relocate(view, "same@A", [2, 0, 0]);
    expect(view.layoutDirty).toBe(true);
    const saved = {
      uid: "view",
      name: "Vista",
      revision: "rev",
      state: studyState(view),
    };
    useSavedView(view, saved);
    view.points["same@A"] = [0, 1, 0];
    expect(saved.state.points["same@A"]).toEqual([1, 0, 0]);
    expect(view.layoutDirty).toBe(false);
  });
});
describe("shared blue palette", () => {
  it("applies the same tokens used by Canvas and verifies representative contrast pairs", () => {
    const host = document.createElement("div");
    applyStudyTheme(host);
    expect(host.style.getPropertyValue("--mm-bg")).toBe(studyTheme.bg);
    for (const [fg, bg] of [
      [studyTheme.text, studyTheme.panel],
      [studyTheme.muted, studyTheme.control],
      [studyTheme["selected-text"], studyTheme["selected-bg"]],
      [studyTheme.error, studyTheme["error-bg"]],
    ])
      expect(contrast(fg, bg)).toBeGreaterThanOrEqual(4.5);
    for (const bg of [studyTheme.bg, studyTheme.panel, studyTheme.control])
      expect(contrast(studyTheme.border, bg)).toBeGreaterThanOrEqual(3);
    expect(contrast("#000000", "#ffffff")).toBe(21);
  });
});
