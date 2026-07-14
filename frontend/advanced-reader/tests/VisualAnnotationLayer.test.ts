import { describe, expect, it, vi } from "vitest";

import {
  VisualAnnotationLayer,
  VisualAnnotationLayerManager,
} from "../src/annotations/VisualAnnotationLayer";
import type { VisualAnnotationRenderItem } from "../src/annotations/types";
import { PdfJsViewportFixture } from "./pdfViewportFixture";

function pageFixture(): {
  annotationLayer: HTMLDivElement;
  canvasWrapper: HTMLDivElement;
  page: HTMLDivElement;
  textLayer: HTMLDivElement;
} {
  const page = document.createElement("div");
  page.className = "page";
  page.dataset.pageNumber = "3";
  const canvasWrapper = document.createElement("div");
  canvasWrapper.className = "canvasWrapper";
  const textLayer = document.createElement("div");
  textLayer.className = "textLayer";
  const annotationLayer = document.createElement("div");
  annotationLayer.className = "annotationLayer";
  page.append(canvasWrapper, textLayer, annotationLayer);
  document.body.append(page);
  return { annotationLayer, canvasWrapper, page, textLayer };
}

function annotation(
  overrides: Partial<VisualAnnotationRenderItem> = {},
): VisualAnnotationRenderItem {
  return {
    annotation_id: "ann_123e4567-e89b-42d3-a456-426614174000",
    kind: "highlight",
    status: "active",
    pdf_page: 3,
    color_label: "blue",
    visual_status: "exact",
    visual_anchor: {
      coordinate_space: "normalized_unrotated_crop_box",
      capture_rotation: 0,
      rects: [{ x: 0.1, y: 0.2, width: 0.3, height: 0.1 }],
    },
    ...overrides,
  };
}

describe("VisualAnnotationLayer", () => {
  it("places multiline highlights between canvas and interactive PDF.js layers", () => {
    const { page, textLayer } = pageFixture();
    const layer = new VisualAnnotationLayer(3, page);
    const viewport = new PdfJsViewportFixture(undefined, 1, 0);
    const item = annotation({
      visual_anchor: {
        coordinate_space: "normalized_unrotated_crop_box",
        capture_rotation: 90,
        rects: [
          { x: 0.1, y: 0.2, width: 0.3, height: 0.04 },
          { x: 0.1, y: 0.25, width: 0.2, height: 0.04 },
        ],
      },
    });

    layer.update(viewport, viewport.clone({ rotation: 0, scale: 1 }), [item]);

    expect([...page.children].map((element) => element.className)).toEqual([
      "canvasWrapper",
      "visualAnnotationLayer",
      "textLayer",
      "annotationLayer",
    ]);
    expect(layer.element).toHaveAttribute("aria-hidden", "true");
    expect(layer.element.style.pointerEvents).toBe("none");
    expect(layer.element.nextElementSibling).toBe(textLayer);
    const marks = [...layer.element.querySelectorAll<HTMLElement>(".visual-annotation-highlight")];
    expect(marks).toHaveLength(2);
    expect(marks[0]).toHaveStyle({ left: "10%", top: "20%", width: "30%", height: "4%" });
    expect(marks[0]?.style.backgroundColor).toBe("rgba(10, 132, 255, 0.27)");
    expect(marks.every((mark) => mark.style.pointerEvents === "none")).toBe(true);
    expect(textLayer).toBeEmptyDOMElement();
  });

  it("draws one bounded underline per canonical rectangle with palette fallback", () => {
    const { page } = pageFixture();
    const layer = new VisualAnnotationLayer(3, page);
    const viewport = new PdfJsViewportFixture(undefined, 2, 0);
    const item = annotation({
      kind: "underline",
      color_label: "legacy-orange",
      visual_anchor: {
        coordinate_space: "normalized_unrotated_crop_box",
        capture_rotation: 0,
        rects: [
          { x: 0.15, y: 0.2, width: 0.25, height: 0.001 },
          { x: 0.15, y: 0.25, width: 0.35, height: 0.001 },
        ],
      },
    });

    layer.update(viewport, viewport.clone({ rotation: 0, scale: 1 }), [item]);

    const marks = [...layer.element.querySelectorAll<HTMLElement>(".visual-annotation-underline")];
    expect(marks).toHaveLength(2);
    expect(marks[0]?.style.backgroundColor).toBe("");
    expect(marks[0]?.style.borderBottomStyle).toBe("solid");
    expect(marks[0]?.style.borderBottomColor).toBe("rgb(161, 113, 0)");
    expect(Number.parseFloat(marks[0]?.style.borderBottomWidth ?? "0")).toBeGreaterThanOrEqual(1);
    expect(Number.parseFloat(marks[0]?.style.borderBottomWidth ?? "4")).toBeLessThanOrEqual(3);
  });

  it("rehydrates exact marks at 90° and remains aligned after zoom and resize", () => {
    const { page } = pageFixture();
    const layer = new VisualAnnotationLayer(3, page);
    const canonicalViewport = new PdfJsViewportFixture(undefined, 1, 0);
    const rotated = new PdfJsViewportFixture(undefined, 1, 90);

    layer.update(rotated, canonicalViewport, [annotation()]);
    const mark = layer.element.querySelector<HTMLElement>(".visual-annotation-mark");
    expect(mark).toHaveStyle({ left: "70%", top: "10%", width: "10%", height: "30%" });
    const firstGeometry = mark?.getAttribute("style");

    layer.update(new PdfJsViewportFixture(undefined, 2.75, 90), canonicalViewport, [annotation()]);
    expect(layer.element.querySelector(".visual-annotation-mark")?.getAttribute("style")).toBe(
      firstGeometry,
    );
    layer.update(new PdfJsViewportFixture(undefined, 0.68, 90), canonicalViewport, [annotation()]);
    expect(layer.element.querySelector(".visual-annotation-mark")?.getAttribute("style")).toBe(
      firstGeometry,
    );
  });

  it("does not draw archived, mismatched, invalid, logical-only, or other-page items", () => {
    const { page } = pageFixture();
    const layer = new VisualAnnotationLayer(3, page);
    const viewport = new PdfJsViewportFixture();

    layer.update(viewport, viewport, [
      annotation({ status: "archived" }),
      annotation({ visual_status: "version_mismatch" }),
      annotation({
        visual_status: "invalid_geometry",
        visual_anchor: {
          coordinate_space: "normalized_unrotated_crop_box",
          capture_rotation: 0,
          rects: [{ x: 0.95, y: 0, width: 0.2, height: 0.1 }],
        },
      }),
      annotation({ visual_status: "logical_only", visual_anchor: null }),
      annotation({ pdf_page: 4 }),
    ]);

    expect(layer.element).toBeEmptyDOMElement();
  });

  it("reattaches after PDF.js resets a page and cleans up through manager lifecycle hooks", () => {
    const { canvasWrapper, page, textLayer } = pageFixture();
    const manager = new VisualAnnotationLayerManager();
    const canonicalViewport = new PdfJsViewportFixture();
    const context = {
      pageNumber: 3,
      pageDiv: page,
      displayedViewport: canonicalViewport,
      unrotatedCropBoxViewport: canonicalViewport,
    };
    manager.setAnnotations([annotation()]);
    const firstLayer = manager.mountPage(context);
    expect(firstLayer.element.querySelectorAll(".visual-annotation-mark")).toHaveLength(1);

    page.replaceChildren(canvasWrapper, textLayer);
    const sameLayer = manager.mountPage({
      ...context,
      displayedViewport: new PdfJsViewportFixture(undefined, 1.8, 180),
    });
    expect(sameLayer).toBe(firstLayer);
    expect(firstLayer.element).toBe(page.querySelector(".visualAnnotationLayer"));
    expect(firstLayer.element.querySelectorAll(".visual-annotation-mark")).toHaveLength(1);

    manager.clear();
    expect(firstLayer.element).toBeEmptyDOMElement();
    manager.removePage(3);
    expect(page.querySelector(".visualAnnotationLayer")).toBeNull();
    manager.destroy();
  });

  it("targets an annotation temporarily without making the overlay interactive", () => {
    vi.useFakeTimers();
    try {
      const { page } = pageFixture();
      const manager = new VisualAnnotationLayerManager();
      const viewport = new PdfJsViewportFixture();
      manager.setAnnotations([annotation()]);
      const layer = manager.mountPage({
        pageNumber: 3,
        pageDiv: page,
        displayedViewport: viewport,
        unrotatedCropBoxViewport: viewport,
      });

      expect(manager.focusAnnotation("ann_123e4567-e89b-42d3-a456-426614174000", 250)).toBe(true);
      const mark = layer.element.querySelector<HTMLElement>(".visual-annotation-mark");
      expect(mark).toHaveClass("is-targeted");
      expect(mark?.style.pointerEvents).toBe("none");

      vi.advanceTimersByTime(249);
      expect(mark).toHaveClass("is-targeted");
      vi.advanceTimersByTime(1);
      expect(mark).not.toHaveClass("is-targeted");
      expect(mark?.style.outline).toBe("");
      manager.destroy();
    } finally {
      vi.useRealTimers();
    }
  });
});
