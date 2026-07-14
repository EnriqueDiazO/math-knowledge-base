import type { NormalizedVisualRect, QuarterTurn } from "./types";

export const MAX_VISUAL_RECTS = 64;
export const VISUAL_GEOMETRY_EPSILON = 1e-9;

export interface ViewportRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** Structural subset of PDF.js PageViewport used by visual annotations. */
export interface PdfJsViewport {
  readonly width: number;
  readonly height: number;
  readonly rotation: number;
  convertToPdfPoint(x: number, y: number): ArrayLike<number>;
  convertToViewportPoint(x: number, y: number): ArrayLike<number>;
  clone?(parameters?: { rotation?: number; scale?: number }): PdfJsViewport;
}

function finite(values: readonly number[]): boolean {
  return values.every(Number.isFinite);
}

function snapUnit(value: number): number {
  if (Math.abs(value) <= VISUAL_GEOMETRY_EPSILON) return 0;
  if (Math.abs(1 - value) <= VISUAL_GEOMETRY_EPSILON) return 1;
  return value;
}

function normalizedRect(value: NormalizedVisualRect): NormalizedVisualRect | null {
  if (!finite([value.x, value.y, value.width, value.height])) return null;
  if (
    value.x < -VISUAL_GEOMETRY_EPSILON ||
    value.y < -VISUAL_GEOMETRY_EPSILON ||
    value.width <= 0 ||
    value.height <= 0 ||
    value.x > 1 + VISUAL_GEOMETRY_EPSILON ||
    value.y > 1 + VISUAL_GEOMETRY_EPSILON ||
    value.x + value.width > 1 + VISUAL_GEOMETRY_EPSILON ||
    value.y + value.height > 1 + VISUAL_GEOMETRY_EPSILON
  ) {
    return null;
  }
  const x = Math.min(1, Math.max(0, snapUnit(value.x)));
  const y = Math.min(1, Math.max(0, snapUnit(value.y)));
  const width = Math.min(1 - x, snapUnit(value.width));
  const height = Math.min(1 - y, snapUnit(value.height));
  return width > 0 && height > 0 ? { x, y, width, height } : null;
}

export function isNormalizedVisualRect(
  value: NormalizedVisualRect,
): value is NormalizedVisualRect {
  return normalizedRect(value) !== null;
}

export function isNormalizedVisualRectList(
  rects: readonly NormalizedVisualRect[],
): boolean {
  return (
    rects.length >= 1 &&
    rects.length <= MAX_VISUAL_RECTS &&
    rects.every(isNormalizedVisualRect)
  );
}

function assertViewport(viewport: PdfJsViewport, label: string): void {
  if (
    !finite([viewport.width, viewport.height]) ||
    viewport.width <= 0 ||
    viewport.height <= 0
  ) {
    throw new RangeError(`${label} must have finite, positive dimensions.`);
  }
}

function point(value: ArrayLike<number>): [number, number] | null {
  const x = Number(value[0]);
  const y = Number(value[1]);
  return finite([x, y]) ? [x, y] : null;
}

function transformedBounds(
  rect: ViewportRect,
  source: PdfJsViewport,
  destination: PdfJsViewport,
): ViewportRect | null {
  if (
    !finite([rect.x, rect.y, rect.width, rect.height]) ||
    rect.width <= 0 ||
    rect.height <= 0
  ) {
    return null;
  }
  const corners = [
    [rect.x, rect.y],
    [rect.x + rect.width, rect.y],
    [rect.x, rect.y + rect.height],
    [rect.x + rect.width, rect.y + rect.height],
  ] as const;
  const converted: [number, number][] = [];
  for (const [x, y] of corners) {
    const pdfPoint = point(source.convertToPdfPoint(x, y));
    if (pdfPoint === null) return null;
    const viewportPoint = point(destination.convertToViewportPoint(pdfPoint[0], pdfPoint[1]));
    if (viewportPoint === null) return null;
    converted.push(viewportPoint);
  }
  const xs = converted.map(([x]) => x);
  const ys = converted.map(([, y]) => y);
  const left = Math.min(...xs);
  const top = Math.min(...ys);
  const right = Math.max(...xs);
  const bottom = Math.max(...ys);
  return right > left && bottom > top
    ? { x: left, y: top, width: right - left, height: bottom - top }
    : null;
}

function viewportRect(value: ViewportRect, viewport: PdfJsViewport): ViewportRect | null {
  if (!finite([value.x, value.y, value.width, value.height])) return null;
  const left = Math.max(0, value.x);
  const top = Math.max(0, value.y);
  const right = Math.min(viewport.width, value.x + value.width);
  const bottom = Math.min(viewport.height, value.y + value.height);
  return right > left && bottom > top
    ? { x: left, y: top, width: right - left, height: bottom - top }
    : null;
}

/**
 * Produces the unrotated CropBox viewport paired with a displayed PDF.js
 * viewport. PDF.js owns CropBox offsets, user-unit handling, and Y-axis flip.
 */
export function createUnrotatedCropBoxViewport(viewport: PdfJsViewport): PdfJsViewport {
  assertViewport(viewport, "Displayed viewport");
  if (typeof viewport.clone !== "function") {
    throw new TypeError("The PDF.js viewport must support clone().");
  }
  const canonicalViewport = viewport.clone({ rotation: 0, scale: 1 });
  assertViewport(canonicalViewport, "Unrotated CropBox viewport");
  return canonicalViewport;
}

export function viewportRectToCanonical(
  value: ViewportRect,
  displayedViewport: PdfJsViewport,
  unrotatedCropBoxViewport: PdfJsViewport,
): NormalizedVisualRect | null {
  assertViewport(displayedViewport, "Displayed viewport");
  assertViewport(unrotatedCropBoxViewport, "Unrotated CropBox viewport");
  const clipped = viewportRect(value, displayedViewport);
  if (clipped === null) return null;
  const converted = transformedBounds(clipped, displayedViewport, unrotatedCropBoxViewport);
  if (converted === null) return null;
  return normalizedRect({
    x: snapUnit(converted.x / unrotatedCropBoxViewport.width),
    y: snapUnit(converted.y / unrotatedCropBoxViewport.height),
    width: snapUnit(converted.width / unrotatedCropBoxViewport.width),
    height: snapUnit(converted.height / unrotatedCropBoxViewport.height),
  });
}

export function normalizedViewportRectToCanonical(
  value: NormalizedVisualRect,
  displayedViewport: PdfJsViewport,
  unrotatedCropBoxViewport: PdfJsViewport,
): NormalizedVisualRect | null {
  const valid = normalizedRect(value);
  if (valid === null) return null;
  return viewportRectToCanonical(
    {
      x: valid.x * displayedViewport.width,
      y: valid.y * displayedViewport.height,
      width: valid.width * displayedViewport.width,
      height: valid.height * displayedViewport.height,
    },
    displayedViewport,
    unrotatedCropBoxViewport,
  );
}

export function normalizedViewportRectsToCanonical(
  rects: readonly NormalizedVisualRect[],
  displayedViewport: PdfJsViewport,
  unrotatedCropBoxViewport: PdfJsViewport,
): NormalizedVisualRect[] | null {
  if (!isNormalizedVisualRectList(rects)) return null;
  const converted = rects.map((rect) =>
    normalizedViewportRectToCanonical(rect, displayedViewport, unrotatedCropBoxViewport),
  );
  return converted.some((rect) => rect === null)
    ? null
    : (converted as NormalizedVisualRect[]);
}

export function canonicalRectToViewport(
  value: NormalizedVisualRect,
  unrotatedCropBoxViewport: PdfJsViewport,
  displayedViewport: PdfJsViewport,
): ViewportRect | null {
  assertViewport(unrotatedCropBoxViewport, "Unrotated CropBox viewport");
  assertViewport(displayedViewport, "Displayed viewport");
  const valid = normalizedRect(value);
  if (valid === null) return null;
  return transformedBounds(
    {
      x: valid.x * unrotatedCropBoxViewport.width,
      y: valid.y * unrotatedCropBoxViewport.height,
      width: valid.width * unrotatedCropBoxViewport.width,
      height: valid.height * unrotatedCropBoxViewport.height,
    },
    unrotatedCropBoxViewport,
    displayedViewport,
  );
}

export function canonicalRectsToViewport(
  rects: readonly NormalizedVisualRect[],
  unrotatedCropBoxViewport: PdfJsViewport,
  displayedViewport: PdfJsViewport,
): ViewportRect[] | null {
  if (!isNormalizedVisualRectList(rects)) return null;
  const converted = rects.map((rect) =>
    canonicalRectToViewport(rect, unrotatedCropBoxViewport, displayedViewport),
  );
  return converted.some((rect) => rect === null) ? null : (converted as ViewportRect[]);
}

export function quarterTurn(value: number): QuarterTurn | null {
  const normalized = ((value % 360) + 360) % 360;
  return normalized === 0 || normalized === 90 || normalized === 180 || normalized === 270
    ? normalized
    : null;
}
