import type {
  NormalizedRect,
  SelectionCaptureContext,
  TextSelectionEvent,
} from "./types";

export const MAX_SELECTED_TEXT_CODE_POINTS = 4096;
export const MAX_SELECTION_RECTS = 64;

function clamp(value: number): number {
  return Math.min(1, Math.max(0, value));
}

function rounded(value: number): number {
  return Math.round(value * 1_000_000) / 1_000_000;
}

export function normalizeSelectedText(value: string): string {
  return Array.from(value.replace(/\s+/gu, " ").trim())
    .slice(0, MAX_SELECTED_TEXT_CODE_POINTS)
    .join("");
}

function elementForNode(node: Node): Element | null {
  if (node.nodeType === Node.ELEMENT_NODE) {
    return node as Element;
  }
  return node.parentElement;
}

function pageForNode(node: Node, viewer: HTMLElement): HTMLElement | null {
  const page = elementForNode(node)?.closest<HTMLElement>(".page[data-page-number]") ?? null;
  return page !== null && viewer.contains(page) ? page : null;
}

function pageNumber(page: HTMLElement): number | null {
  const value = Number(page.dataset.pageNumber);
  return Number.isInteger(value) && value >= 1 ? value : null;
}

function normalizeRect(rect: DOMRect, pageRect: DOMRect): NormalizedRect | null {
  const values = [
    pageRect.left,
    pageRect.top,
    pageRect.right,
    pageRect.bottom,
    pageRect.width,
    pageRect.height,
    rect.left,
    rect.top,
    rect.right,
    rect.bottom,
    rect.width,
    rect.height,
  ];
  if (
    values.some((value) => !Number.isFinite(value)) ||
    pageRect.width <= 0 ||
    pageRect.height <= 0 ||
    rect.width <= 0 ||
    rect.height <= 0
  ) {
    return null;
  }
  const left = Math.max(rect.left, pageRect.left);
  const top = Math.max(rect.top, pageRect.top);
  const right = Math.min(rect.right, pageRect.right);
  const bottom = Math.min(rect.bottom, pageRect.bottom);
  if (right <= left || bottom <= top) {
    return null;
  }
  const x = rounded(clamp((left - pageRect.left) / pageRect.width));
  const y = rounded(clamp((top - pageRect.top) / pageRect.height));
  const normalized = {
    x,
    y,
    width: rounded(Math.min(1 - x, clamp((right - left) / pageRect.width))),
    height: rounded(Math.min(1 - y, clamp((bottom - top) / pageRect.height))),
  };
  if (
    Object.values(normalized).some((value) => !Number.isFinite(value)) ||
    normalized.width <= 0 ||
    normalized.height <= 0
  ) {
    return null;
  }
  return normalized;
}

function baseEvent(
  selectedText: string,
  context: SelectionCaptureContext,
): Omit<
  TextSelectionEvent,
  "pdf_page" | "rects_normalized" | "cross_page" | "geometry_status"
> {
  const rotation = [0, 90, 180, 270].includes(context.rotation)
    ? (context.rotation as 0 | 90 | 180 | 270)
    : 0;
  const scale = Number.isFinite(context.scale)
    ? Math.min(5, Math.max(0.25, context.scale))
    : 1;
  return {
    schema_version: 1,
    event_type: "text_selection",
    document_id: context.documentId,
    version_id: context.versionId,
    selected_text: selectedText,
    rotation,
    scale,
  };
}

export function captureTextSelection(
  selection: Selection | null,
  viewer: HTMLElement,
  context: SelectionCaptureContext,
): TextSelectionEvent | null {
  if (selection === null || selection.isCollapsed || selection.rangeCount === 0) {
    return null;
  }
  const selectedText = normalizeSelectedText(selection.toString());
  if (!selectedText) {
    return null;
  }

  const firstRange = selection.getRangeAt(0);
  const lastRange = selection.getRangeAt(selection.rangeCount - 1);
  const startPage = pageForNode(firstRange.startContainer, viewer);
  const endPage = pageForNode(lastRange.endContainer, viewer);
  const common = baseEvent(selectedText, context);

  if (startPage === null || endPage === null) {
    return {
      ...common,
      pdf_page: null,
      rects_normalized: [],
      cross_page: false,
      geometry_status: "unresolved",
    };
  }
  if (startPage !== endPage || selection.rangeCount > 1) {
    return {
      ...common,
      pdf_page: null,
      rects_normalized: [],
      cross_page: true,
      geometry_status: "cross_page",
    };
  }

  const pdfPage = pageNumber(startPage);
  if (pdfPage === null) {
    return {
      ...common,
      pdf_page: null,
      rects_normalized: [],
      cross_page: false,
      geometry_status: "unresolved",
    };
  }

  const pageRect = startPage.getBoundingClientRect();
  const clientRects = Array.from(firstRange.getClientRects());
  if (clientRects.length > MAX_SELECTION_RECTS) {
    return {
      ...common,
      pdf_page: null,
      rects_normalized: [],
      cross_page: false,
      geometry_status: "unresolved",
    };
  }
  const rects = clientRects
    .map((rect) => normalizeRect(rect, pageRect))
    .filter((rect): rect is NormalizedRect => rect !== null);

  if (rects.length === 0) {
    return {
      ...common,
      pdf_page: null,
      rects_normalized: [],
      cross_page: false,
      geometry_status: "unresolved",
    };
  }
  return {
    ...common,
    pdf_page: pdfPage,
    rects_normalized: rects,
    cross_page: false,
    geometry_status: "valid",
  };
}

export function clearBrowserSelection(): void {
  window.getSelection()?.removeAllRanges();
}
