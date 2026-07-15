import { vi } from "vitest";

import type {
  NormalizedVisualRect,
  VisualAnnotationRenderItem,
} from "../src/annotations/types";
import type { AdvancedReaderApi } from "../src/api/client";
import type {
  PdfControllerMountOptions,
  PdfReaderController,
  ScaleMode,
  SearchDirection,
  SearchOptions,
  SearchUpdate,
} from "../src/pdf/types";
import type { TextSelectionEvent } from "../src/selection/types";
import type { DocumentMetadata, PageLabel } from "../src/types/api";
import type { PageChangeOrigin, SelectionClearReason } from "../src/types/events";

export const DOCUMENT_ID = "doc_123e4567-e89b-42d3-a456-426614174000";
export const VERSION_ID = "dver_123e4567-e89b-42d3-a456-426614174001";

export const metadata: DocumentMetadata = {
  document_id: DOCUMENT_ID,
  title: "Geometría diferencial",
  kind: "pdf",
  status: "active",
  source: { source_id: "src_local", name: "Biblioteca personal" },
  reference: { reference_id: "ref_local", title: "Notas de variedades" },
  version: {
    version_id: VERSION_ID,
    sha256: "a".repeat(64),
    size_bytes: 2_621_440,
    original_filename: "variedades.pdf",
  },
  reading_state: {
    status: "in_progress",
    current_page: 3,
    total_pages: 12,
    last_opened_at: "2026-07-13T12:00:00Z",
  },
  page_label: { pdf_page: 3, book_page_label: "1", display_label: "Book page 1 · PDF page 3" },
  capabilities: {
    page_navigation: true,
    thumbnails: true,
    zoom: true,
    rotate: true,
    text_search: true,
    text_selection: true,
    temporary_selection_geometry: true,
    persistent_highlights: false,
    persistent_underlines: false,
    visual_annotation_editing: false,
    visual_annotation_archiving: false,
    concept_search: false,
    annotation_concept_links: false,
    concept_link_archive: false,
    concept_link_reactivate: false,
    concept_linking: false,
  },
};

export function pageLabel(pdfPage: number): PageLabel {
  return {
    pdf_page: pdfPage,
    book_page_label: String(pdfPage - 2),
    display_label: `Book page ${pdfPage - 2} · PDF page ${pdfPage}`,
  };
}

export function makeApi(overrides: Partial<AdvancedReaderApi> = {}): AdvancedReaderApi {
  return {
    getMetadata: vi.fn().mockResolvedValue(metadata),
    getPageLabel: vi.fn((_documentId: string, pdfPage: number) =>
      Promise.resolve(pageLabel(pdfPage))),
    savePage: vi.fn().mockResolvedValue({
      document_id: DOCUMENT_ID,
      status: "in_progress",
      current_page: 3,
      total_pages: 12,
      last_opened_at: "2026-07-13T12:00:00Z",
    }),
    listVisualAnnotations: vi.fn().mockResolvedValue({
      items: [], page: 1, page_size: 50, total: 0, pages: 0,
    }),
    createVisualAnnotation: vi.fn(),
    getVisualAnnotation: vi.fn(),
    updateVisualAnnotation: vi.fn(),
    archiveVisualAnnotation: vi.fn(),
    reactivateVisualAnnotation: vi.fn(),
    searchConcepts: vi.fn().mockResolvedValue({ items: [], page: 1, page_size: 20, has_more: false }),
    listAnnotationConceptEvidence: vi.fn().mockResolvedValue({
      items: [], page: 1, page_size: 25, total: 0, pages: 0,
    }),
    createAnnotationConceptEvidence: vi.fn(),
    archiveConceptEvidence: vi.fn(),
    reactivateConceptEvidence: vi.fn(),
    listDocumentConceptEvidence: vi.fn().mockResolvedValue({
      items: [], page: 1, page_size: 25, total: 0, pages: 0,
    }),
    listUnlinkedVisualAnnotations: vi.fn().mockResolvedValue({
      items: [], page: 1, page_size: 25, total: 0, pages: 0,
    }),
    pdfUrl: vi.fn(() => `/api/advanced-reader/documents/${DOCUMENT_ID}/pdf`),
    ...overrides,
  };
}

export class FakePdfController implements PdfReaderController {
  options: PdfControllerMountOptions | null = null;
  page = 3;
  total = 12;
  scale = 1;
  rotation = 0;
  visualAnnotations: readonly VisualAnnotationRenderItem[] = [];

  constructor(readonly autoPaint = true) {}

  readonly mount = vi.fn(async (options: PdfControllerMountOptions) => {
    this.options = options;
    this.page = options.initialPage;
    const thumbnail = document.createElement("button");
    thumbnail.type = "button";
    thumbnail.textContent = "p. 7";
    thumbnail.setAttribute("aria-label", "Ir a PDF page 7");
    thumbnail.addEventListener("click", () => this.goToPage(7, "thumbnail"));
    options.thumbnails.append(thumbnail);
    options.handlers.onReady(this.total);
    options.handlers.onPageChanged(this.page, "initial");
    options.handlers.onZoomChanged(this.scale);
    if (this.autoPaint) options.handlers.onPageRendered(this.page);
  });
  readonly destroy = vi.fn(() => undefined);
  readonly goToPage = vi.fn((page: number, origin: PageChangeOrigin = "toolbar") => {
    this.page = Math.min(this.total, Math.max(1, Math.trunc(page)));
    this.options?.handlers.onSelectionChanged(null, "page_change");
    this.options?.handlers.onPageChanged(this.page, origin);
  });
  readonly previousPage = vi.fn(() => this.goToPage(this.page - 1, "toolbar"));
  readonly nextPage = vi.fn(() => this.goToPage(this.page + 1, "toolbar"));
  readonly zoomIn = vi.fn(() => {
    this.scale = Math.min(5, this.scale * 1.1);
    this.options?.handlers.onZoomChanged(this.scale);
  });
  readonly zoomOut = vi.fn(() => {
    this.scale = Math.max(0.25, this.scale / 1.1);
    this.options?.handlers.onZoomChanged(this.scale);
  });
  readonly setScaleMode = vi.fn((_mode: ScaleMode) => undefined);
  readonly rotateClockwise = vi.fn(() => {
    this.options?.handlers.onSelectionChanged(null, "rotation_change");
    this.rotation = (this.rotation + 90) % 360;
    this.options?.handlers.onRotationChanged(this.rotation, "clockwise");
  });
  readonly rotateCounterclockwise = vi.fn(() => {
    this.options?.handlers.onSelectionChanged(null, "rotation_change");
    this.rotation = (this.rotation + 270) % 360;
    this.options?.handlers.onRotationChanged(this.rotation, "counterclockwise");
  });
  readonly retryPage = vi.fn((page: number) => {
    this.options?.handlers.onPageRendered(page);
  });
  readonly setVisualAnnotations = vi.fn((annotations: readonly VisualAnnotationRenderItem[]) => {
    this.visualAnnotations = [...annotations];
  });
  readonly canonicalizeSelection = vi.fn(
    (_pdfPage: number, rects: readonly NormalizedVisualRect[]) => rects.map((rect) => ({ ...rect })),
  );
  readonly focusVisualAnnotation = vi.fn((annotationId: string) => {
    const annotation = this.visualAnnotations.find((item) => item.annotation_id === annotationId);
    if (annotation !== undefined) this.goToPage(annotation.pdf_page, "pdfjs");
  });
  readonly search = vi.fn(
    (query: string, _direction: SearchDirection, _options: SearchOptions, _again: boolean) => {
      this.options?.handlers.onSearchChanged({
        status: query ? "pending" : "idle",
        current: 0,
        total: 0,
      });
    },
  );
  readonly clearSelection = vi.fn((reason: SelectionClearReason = "user") =>
    this.options?.handlers.onSelectionChanged(null, reason));

  emitSearch(update: SearchUpdate): void {
    this.options?.handlers.onSearchChanged(update);
  }

  emitSelection(selection: TextSelectionEvent): void {
    this.options?.handlers.onSelectionChanged(selection);
  }
}

export const samePageSelection: TextSelectionEvent = {
  schema_version: 1,
  event_type: "text_selection",
  document_id: DOCUMENT_ID,
  version_id: VERSION_ID,
  pdf_page: 3,
  selected_text: "Toda variedad compacta admite una métrica.",
  rects_normalized: [{ x: 0.1, y: 0.2, width: 0.5, height: 0.04 }],
  rotation: 0,
  scale: 1,
  cross_page: false,
  geometry_status: "valid",
};

export const crossPageSelection: TextSelectionEvent = {
  ...samePageSelection,
  pdf_page: null,
  rects_normalized: [],
  cross_page: true,
  geometry_status: "cross_page",
};
