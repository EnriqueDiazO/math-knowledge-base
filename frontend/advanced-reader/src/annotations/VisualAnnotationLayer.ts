import {
  canonicalRectsToViewport,
  type PdfJsViewport,
  quarterTurn,
} from "./geometry";
import {
  VISUAL_ANNOTATION_COORDINATE_SPACE,
  type VisualAnnotationKind,
  type VisualAnnotationRenderItem,
  type VisualColorLabel,
} from "./types";

interface VisualColorStyle {
  fill: string;
  stroke: string;
}

const COLOR_STYLES: Readonly<Record<VisualColorLabel, VisualColorStyle>> = Object.freeze({
  yellow: { fill: "rgba(255, 214, 10, 0.34)", stroke: "rgb(161, 113, 0)" },
  green: { fill: "rgba(48, 209, 88, 0.28)", stroke: "rgb(20, 112, 45)" },
  blue: { fill: "rgba(10, 132, 255, 0.27)", stroke: "rgb(0, 82, 164)" },
  pink: { fill: "rgba(255, 55, 95, 0.25)", stroke: "rgb(174, 28, 67)" },
  purple: { fill: "rgba(175, 82, 222, 0.25)", stroke: "rgb(111, 39, 146)" },
});

export interface VisualAnnotationPageContext {
  pageNumber: number;
  pageDiv: HTMLDivElement;
  displayedViewport: PdfJsViewport;
  unrotatedCropBoxViewport: PdfJsViewport;
}

function colorStyle(label: string): VisualColorStyle {
  return Object.hasOwn(COLOR_STYLES, label)
    ? COLOR_STYLES[label as VisualColorLabel]
    : COLOR_STYLES.yellow;
}

function percentage(value: number, dimension: number): string {
  const percent = Math.min(100, Math.max(0, (value / dimension) * 100));
  return `${Math.round(percent * 1e8) / 1e8}%`;
}

function createRoot(pageNumber: number): HTMLDivElement {
  const root = document.createElement("div");
  root.className = "visualAnnotationLayer";
  root.dataset.pageNumber = String(pageNumber);
  root.setAttribute("aria-hidden", "true");
  root.style.position = "absolute";
  root.style.inset = "0";
  root.style.overflow = "hidden";
  root.style.pointerEvents = "none";
  root.style.userSelect = "none";
  root.style.zIndex = "0";
  root.style.contain = "layout paint style";
  return root;
}

function placeBeforeInteractivePdfLayers(pageDiv: HTMLDivElement, root: HTMLDivElement): void {
  const nextLayer = pageDiv.querySelector(
    ":scope > .textLayer, :scope > .annotationLayer, :scope > .annotationEditorLayer",
  );
  if (nextLayer === null) pageDiv.append(root);
  else pageDiv.insertBefore(root, nextLayer);
}

function markElement(
  annotation: VisualAnnotationRenderItem,
  kind: VisualAnnotationKind,
  rectIndex: number,
): HTMLDivElement {
  const mark = document.createElement("div");
  mark.className = `visual-annotation-mark visual-annotation-${kind}`;
  mark.dataset.annotationId = annotation.annotation_id;
  mark.dataset.rectIndex = String(rectIndex);
  mark.dataset.kind = kind;
  mark.style.position = "absolute";
  mark.style.boxSizing = "border-box";
  mark.style.pointerEvents = "none";
  return mark;
}

export class VisualAnnotationLayer {
  readonly #pageNumber: number;
  #pageDiv: HTMLDivElement;
  readonly #root: HTMLDivElement;

  constructor(pageNumber: number, pageDiv: HTMLDivElement) {
    if (!Number.isInteger(pageNumber) || pageNumber < 1) {
      throw new RangeError("Visual annotation pageNumber must be a positive integer.");
    }
    this.#pageNumber = pageNumber;
    this.#pageDiv = pageDiv;
    this.#root = createRoot(pageNumber);
    placeBeforeInteractivePdfLayers(pageDiv, this.#root);
  }

  get element(): HTMLDivElement {
    return this.#root;
  }

  belongsTo(pageDiv: HTMLDivElement): boolean {
    return this.#pageDiv === pageDiv;
  }

  update(
    displayedViewport: PdfJsViewport,
    unrotatedCropBoxViewport: PdfJsViewport,
    annotations: readonly VisualAnnotationRenderItem[],
  ): void {
    placeBeforeInteractivePdfLayers(this.#pageDiv, this.#root);
    this.#root.replaceChildren();
    this.#root.dataset.rotation = String(quarterTurn(displayedViewport.rotation) ?? 0);

    for (const annotation of annotations) {
      const anchor = annotation.visual_anchor;
      if (
        annotation.pdf_page !== this.#pageNumber ||
        annotation.status !== "active" ||
        annotation.visual_status !== "exact" ||
        anchor === null ||
        anchor.coordinate_space !== VISUAL_ANNOTATION_COORDINATE_SPACE
      ) {
        continue;
      }
      const rects = canonicalRectsToViewport(
        anchor.rects,
        unrotatedCropBoxViewport,
        displayedViewport,
      );
      if (rects === null) continue;
      const palette = colorStyle(annotation.color_label);
      rects.forEach((rect, rectIndex) => {
        const mark = markElement(annotation, annotation.kind, rectIndex);
        mark.style.left = percentage(rect.x, displayedViewport.width);
        mark.style.top = percentage(rect.y, displayedViewport.height);
        mark.style.width = percentage(rect.width, displayedViewport.width);
        mark.style.height = percentage(rect.height, displayedViewport.height);
        if (annotation.kind === "highlight") {
          mark.style.backgroundColor = palette.fill;
        } else {
          const thickness = Math.min(3, Math.max(1, rect.height * 0.08));
          mark.style.borderBottomColor = palette.stroke;
          mark.style.borderBottomStyle = "solid";
          mark.style.borderBottomWidth = `${Math.round(thickness * 1000) / 1000}px`;
        }
        this.#root.append(mark);
      });
    }
  }

  setFocusedAnnotation(annotationId: string | null): boolean {
    let matched = false;
    for (const mark of this.#root.querySelectorAll<HTMLElement>(".visual-annotation-mark")) {
      const focused = annotationId !== null && mark.dataset.annotationId === annotationId;
      mark.classList.toggle("is-targeted", focused);
      mark.style.outline = focused ? "2px solid rgb(0, 95, 184)" : "";
      mark.style.outlineOffset = focused ? "1px" : "";
      if (focused) matched = true;
    }
    return matched;
  }

  destroy(): void {
    this.#root.remove();
    this.#root.replaceChildren();
  }
}

/**
 * Lifecycle adapter for PDF.js page views. A controller can call mountPage on
 * pagerendered/scale/rotation updates without coupling API state to PDF.js.
 */
export class VisualAnnotationLayerManager {
  readonly #layers = new Map<number, VisualAnnotationLayer>();
  readonly #contexts = new Map<number, VisualAnnotationPageContext>();
  #annotations: readonly VisualAnnotationRenderItem[] = [];
  #focusTimer: number | null = null;
  #focusedAnnotationId: string | null = null;

  setAnnotations(annotations: readonly VisualAnnotationRenderItem[]): void {
    this.#annotations = [...annotations];
    for (const [pageNumber, context] of this.#contexts) {
      this.#layers.get(pageNumber)?.update(
        context.displayedViewport,
        context.unrotatedCropBoxViewport,
        this.#annotations,
      );
      this.#layers.get(pageNumber)?.setFocusedAnnotation(this.#focusedAnnotationId);
    }
  }

  mountPage(context: VisualAnnotationPageContext): VisualAnnotationLayer {
    if (!Number.isInteger(context.pageNumber) || context.pageNumber < 1) {
      throw new RangeError("Visual annotation pageNumber must be a positive integer.");
    }
    let layer = this.#layers.get(context.pageNumber);
    if (layer !== undefined && !layer.belongsTo(context.pageDiv)) {
      layer.destroy();
      this.#layers.delete(context.pageNumber);
      layer = undefined;
    }
    layer ??= new VisualAnnotationLayer(context.pageNumber, context.pageDiv);
    this.#layers.set(context.pageNumber, layer);
    this.#contexts.set(context.pageNumber, context);
    layer.update(
      context.displayedViewport,
      context.unrotatedCropBoxViewport,
      this.#annotations,
    );
    layer.setFocusedAnnotation(this.#focusedAnnotationId);
    return layer;
  }

  pageForAnnotation(annotationId: string): number | null {
    const annotation = this.#annotations.find(
      (item) =>
        item.annotation_id === annotationId &&
        item.status === "active" &&
        item.visual_status === "exact" &&
        item.visual_anchor !== null,
    );
    return annotation?.pdf_page ?? null;
  }

  hasPage(pageNumber: number): boolean {
    return this.#layers.has(pageNumber);
  }

  mountedPageNumbers(): number[] {
    return [...this.#layers.keys()];
  }

  focusAnnotation(annotationId: string, durationMs = 1_800): boolean {
    if (this.#focusTimer !== null) {
      window.clearTimeout(this.#focusTimer);
      this.#focusTimer = null;
    }
    this.#focusedAnnotationId = annotationId;
    let matched = false;
    for (const layer of this.#layers.values()) {
      matched = layer.setFocusedAnnotation(annotationId) || matched;
    }
    if (!matched) {
      this.#focusedAnnotationId = null;
      return false;
    }
    this.#focusTimer = window.setTimeout(() => {
      this.#focusTimer = null;
      this.#focusedAnnotationId = null;
      for (const layer of this.#layers.values()) layer.setFocusedAnnotation(null);
    }, Math.max(250, Math.min(10_000, durationMs)));
    return true;
  }

  removePage(pageNumber: number): void {
    this.#layers.get(pageNumber)?.destroy();
    this.#layers.delete(pageNumber);
    this.#contexts.delete(pageNumber);
  }

  clear(): void {
    this.setAnnotations([]);
  }

  destroy(): void {
    if (this.#focusTimer !== null) {
      window.clearTimeout(this.#focusTimer);
      this.#focusTimer = null;
    }
    this.#focusedAnnotationId = null;
    for (const layer of this.#layers.values()) layer.destroy();
    this.#layers.clear();
    this.#contexts.clear();
    this.#annotations = [];
  }
}
