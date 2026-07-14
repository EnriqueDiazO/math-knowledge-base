import { describe, expect, it, vi } from "vitest";

import {
  MAX_SELECTION_RECTS,
  MAX_SELECTED_TEXT_CODE_POINTS,
  captureTextSelection,
} from "../src/selection/captureSelection";
import { DOCUMENT_ID, VERSION_ID } from "./fixtures";

function selectionFixture(text: string, rects: DOMRect[]) {
  const viewer = document.createElement("div");
  const page = document.createElement("div");
  page.className = "page";
  page.dataset.pageNumber = "9";
  const span = document.createElement("span");
  span.textContent = text;
  page.append(span);
  viewer.append(page);
  document.body.append(viewer);
  vi.spyOn(page, "getBoundingClientRect").mockReturnValue(
    new DOMRect(100, 200, 400, 800),
  );
  const range = {
    startContainer: span.firstChild as Node,
    endContainer: span.firstChild as Node,
    getClientRects: () => rects,
  } as unknown as Range;
  const selection = {
    isCollapsed: false,
    rangeCount: 1,
    toString: () => text,
    getRangeAt: () => range,
  } as unknown as Selection;
  return { viewer, selection };
}

const context = {
  documentId: DOCUMENT_ID,
  versionId: VERSION_ID,
  rotation: 90,
  scale: 1.25,
};

describe("ephemeral selection geometry", () => {
  it("[58] clips and normalizes selection rectangles to the rendered page", () => {
    const { viewer, selection } = selectionFixture(
      "  texto   normalizado  ",
      [new DOMRect(140, 280, 200, 40), new DOMRect(480, 960, 80, 80)],
    );
    const result = captureTextSelection(selection, viewer, context);

    expect(result).toMatchObject({
      pdf_page: 9,
      selected_text: "texto normalizado",
      rotation: 90,
      scale: 1.25,
      geometry_status: "valid",
    });
    expect(result?.rects_normalized).toEqual([
      { x: 0.1, y: 0.1, width: 0.5, height: 0.05 },
      { x: 0.95, y: 0.95, width: 0.05, height: 0.05 },
    ]);
  });

  it("[59] caps selected text by Unicode code point without splitting emoji", () => {
    const oversized = `  ${"∫ ".repeat(MAX_SELECTED_TEXT_CODE_POINTS + 50)}😀  `;
    const { viewer, selection } = selectionFixture(oversized, [new DOMRect(110, 210, 20, 20)]);
    const result = captureTextSelection(selection, viewer, context);

    expect(Array.from(result?.selected_text ?? "")).toHaveLength(MAX_SELECTED_TEXT_CODE_POINTS);
    expect(result?.selected_text).not.toMatch(/\s{2,}/u);
  });

  it("caps normalized geometry at the documented 64 rectangles", () => {
    const rects = Array.from(
      { length: MAX_SELECTION_RECTS + 12 },
      (_, index) => new DOMRect(110, 210 + index * 2, 20, 1),
    );
    const { viewer, selection } = selectionFixture("rectángulos", rects);
    const result = captureTextSelection(selection, viewer, context);

    expect(result?.rects_normalized).toHaveLength(MAX_SELECTION_RECTS);
  });

  it("discards non-finite and rounded-to-zero rectangles", () => {
    const { viewer, selection } = selectionFixture("geometría finita", [
      new DOMRect(Number.NaN, 210, 20, 20),
      new DOMRect(110, 210, Number.POSITIVE_INFINITY, 20),
      new DOMRect(110, 210, 0.00000001, 20),
      new DOMRect(120, 220, 40, 30),
    ]);
    const result = captureTextSelection(selection, viewer, context);

    expect(result?.geometry_status).toBe("valid");
    expect(result?.rects_normalized).toEqual([
      { x: 0.05, y: 0.025, width: 0.1, height: 0.0375 },
    ]);
    expect(
      result?.rects_normalized.every((rect) =>
        Object.values(rect).every(Number.isFinite)),
    ).toBe(true);
  });

  it("marks geometry unresolved when every rectangle is unusable", () => {
    const { viewer, selection } = selectionFixture(
      "sin geometría",
      [new DOMRect(110, 210, 0.00000001, 20)],
    );
    const result = captureTextSelection(selection, viewer, context);

    expect(result).toMatchObject({
      pdf_page: null,
      rects_normalized: [],
      cross_page: false,
      geometry_status: "unresolved",
    });
  });
});
