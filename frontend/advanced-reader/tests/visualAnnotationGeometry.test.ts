import { describe, expect, it } from "vitest";

import {
  MAX_VISUAL_RECTS,
  canonicalRectToViewport,
  canonicalRectsToViewport,
  createUnrotatedCropBoxViewport,
  normalizedViewportRectToCanonical,
  normalizedViewportRectsToCanonical,
  viewportRectToCanonical,
} from "../src/annotations/geometry";
import type { NormalizedVisualRect } from "../src/annotations/types";
import { PdfJsViewportFixture } from "./pdfViewportFixture";

const CANONICAL_RECT: NormalizedVisualRect = {
  x: 0.1,
  y: 0.2,
  width: 0.3,
  height: 0.1,
};

const ROTATED_NORMALIZED: Record<number, NormalizedVisualRect> = {
  0: { x: 0.1, y: 0.2, width: 0.3, height: 0.1 },
  90: { x: 0.7, y: 0.1, width: 0.1, height: 0.3 },
  180: { x: 0.6, y: 0.7, width: 0.3, height: 0.1 },
  270: { x: 0.2, y: 0.6, width: 0.1, height: 0.3 },
};

function expectRectClose(actual: NormalizedVisualRect | null, expected: NormalizedVisualRect): void {
  expect(actual).not.toBeNull();
  expect(actual?.x).toBeCloseTo(expected.x, 10);
  expect(actual?.y).toBeCloseTo(expected.y, 10);
  expect(actual?.width).toBeCloseTo(expected.width, 10);
  expect(actual?.height).toBeCloseTo(expected.height, 10);
}

function asNormalized(
  rect: { x: number; y: number; width: number; height: number } | null,
  viewport: PdfJsViewportFixture,
): NormalizedVisualRect | null {
  return rect === null
    ? null
    : {
        x: rect.x / viewport.width,
        y: rect.y / viewport.height,
        width: rect.width / viewport.width,
        height: rect.height / viewport.height,
      };
}

describe("normalized_unrotated_crop_box geometry", () => {
  it.each([0, 90, 180, 270] as const)(
    "converts canonical rectangles through a PDF.js %d° viewport",
    (rotation) => {
      const canonicalViewport = new PdfJsViewportFixture(undefined, 1, 0);
      const displayedViewport = new PdfJsViewportFixture(undefined, 2.25, rotation);

      expectRectClose(
        asNormalized(
          canonicalRectToViewport(CANONICAL_RECT, canonicalViewport, displayedViewport),
          displayedViewport,
        ),
        ROTATED_NORMALIZED[rotation],
      );
      expectRectClose(
        normalizedViewportRectToCanonical(
          ROTATED_NORMALIZED[rotation],
          displayedViewport,
          canonicalViewport,
        ),
        CANONICAL_RECT,
      );
    },
  );

  it.each([0, 90, 180, 270] as const)(
    "round-trips viewport → canonical → viewport at %d°",
    (rotation) => {
      const displayedViewport = new PdfJsViewportFixture(undefined, 1.73, rotation);
      const canonicalViewport = createUnrotatedCropBoxViewport(displayedViewport);
      const source = ROTATED_NORMALIZED[rotation];
      const canonical = normalizedViewportRectToCanonical(
        source,
        displayedViewport,
        canonicalViewport,
      );
      expect(canonical).not.toBeNull();
      const result = canonical === null
        ? null
        : asNormalized(
            canonicalRectToViewport(canonical, canonicalViewport, displayedViewport),
            displayedViewport,
          );
      expectRectClose(result, source);
    },
  );

  it.each([0, 90, 180, 270] as const)(
    "round-trips canonical → viewport → canonical at %d°",
    (rotation) => {
      const displayedViewport = new PdfJsViewportFixture(undefined, 2.19, rotation);
      const canonicalViewport = createUnrotatedCropBoxViewport(displayedViewport);
      const displayed = canonicalRectToViewport(
        CANONICAL_RECT,
        canonicalViewport,
        displayedViewport,
      );

      expectRectClose(
        displayed === null
          ? null
          : viewportRectToCanonical(
              displayed,
              displayedViewport,
              canonicalViewport,
            ),
        CANONICAL_RECT,
      );
    },
  );

  it("preserves multiline rectangles and their order", () => {
    const displayedViewport = new PdfJsViewportFixture(undefined, 2, 90);
    const canonicalViewport = createUnrotatedCropBoxViewport(displayedViewport);
    const lines = [
      { x: 0.65, y: 0.08, width: 0.04, height: 0.32 },
      { x: 0.55, y: 0.08, width: 0.04, height: 0.24 },
      { x: 0.45, y: 0.08, width: 0.04, height: 0.15 },
    ];

    const canonical = normalizedViewportRectsToCanonical(
      lines,
      displayedViewport,
      canonicalViewport,
    );
    expect(canonical).toHaveLength(3);
    const rehydrated = canonical === null
      ? null
      : canonicalRectsToViewport(canonical, canonicalViewport, displayedViewport)?.map((rect) =>
          asNormalized(rect, displayedViewport),
        );
    expect(rehydrated).not.toBeNull();
    rehydrated?.forEach((rect, index) => expectRectClose(rect, lines[index]));
  });

  it.each([
    ["actual size", 1],
    ["fit page", 0.72],
    ["fit width", 1.64],
    ["zoom", 3.25],
    ["resize", 2.05],
  ] as const)("keeps canonical geometry invariant under %s", (_mode, scale) => {
    const displayedViewport = new PdfJsViewportFixture(undefined, scale, 270);
    const canonicalViewport = createUnrotatedCropBoxViewport(displayedViewport);

    expectRectClose(
      normalizedViewportRectToCanonical(
        ROTATED_NORMALIZED[270],
        displayedViewport,
        canonicalViewport,
      ),
      CANONICAL_RECT,
    );
  });

  it("uses PDF.js point transforms for a CropBox with non-zero origin", () => {
    const displayedViewport = new PdfJsViewportFixture([125, -40, 725, 760], 2, 180);
    const canonicalViewport = createUnrotatedCropBoxViewport(displayedViewport);
    const viewportRect = canonicalRectToViewport(
      CANONICAL_RECT,
      canonicalViewport,
      displayedViewport,
    );

    expectRectClose(
      viewportRect === null
        ? null
        : viewportRectToCanonical(viewportRect, displayedViewport, canonicalViewport),
      CANONICAL_RECT,
    );
  });

  it("clips viewport rectangles to the displayed page before canonicalizing", () => {
    const displayedViewport = new PdfJsViewportFixture(undefined, 1, 0);
    const canonicalViewport = createUnrotatedCropBoxViewport(displayedViewport);

    expectRectClose(
      viewportRectToCanonical(
        { x: -60, y: -80, width: 180, height: 240 },
        displayedViewport,
        canonicalViewport,
      ),
      { x: 0, y: 0, width: 0.2, height: 0.2 },
    );
  });

  it("rejects invalid, empty, non-finite, and oversized geometry", () => {
    const displayedViewport = new PdfJsViewportFixture();
    const canonicalViewport = createUnrotatedCropBoxViewport(displayedViewport);

    expect(normalizedViewportRectsToCanonical([], displayedViewport, canonicalViewport)).toBeNull();
    expect(
      normalizedViewportRectsToCanonical(
        Array.from({ length: MAX_VISUAL_RECTS + 1 }, () => CANONICAL_RECT),
        displayedViewport,
        canonicalViewport,
      ),
    ).toBeNull();
    for (const rect of [
      { x: Number.NaN, y: 0, width: 0.1, height: 0.1 },
      { x: 0, y: 0, width: Number.POSITIVE_INFINITY, height: 0.1 },
      { x: -0.1, y: 0, width: 0.1, height: 0.1 },
      { x: 0.95, y: 0, width: 0.1, height: 0.1 },
      { x: 0, y: 0, width: 0, height: 0.1 },
    ]) {
      expect(
        normalizedViewportRectToCanonical(rect, displayedViewport, canonicalViewport),
      ).toBeNull();
    }
  });
});
