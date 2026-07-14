import type {
  NormalizedVisualRect,
  VisualAnnotationRenderItem,
} from "../annotations/types";
import type { TextSelectionEvent } from "../selection/types";
import type {
  PageChangeOrigin,
  SelectionClearReason,
} from "../types/events";

export type ScaleMode = "page-width" | "page-fit" | "page-actual";
export type SearchDirection = "next" | "previous";
export type SearchStatus = "idle" | "pending" | "found" | "not_found" | "wrapped";

export interface SearchOptions {
  caseSensitive: boolean;
  entireWord: boolean;
}

export interface SearchUpdate {
  status: SearchStatus;
  current: number;
  total: number;
}

export interface PdfControllerHandlers {
  onReady(totalPages: number): void;
  onPageRendered(pdfPage: number): void;
  onPageRenderFailed(pdfPage: number): void;
  onPageChanged(pdfPage: number, origin: PageChangeOrigin): void;
  onZoomChanged(scale: number): void;
  onRotationChanged(rotation: number, direction: "clockwise" | "counterclockwise"): void;
  onSearchChanged(update: SearchUpdate): void;
  onSelectionChanged(
    selection: TextSelectionEvent | null,
    reason?: SelectionClearReason,
  ): void;
  onError(): void;
}

export interface PdfControllerMountOptions {
  container: HTMLDivElement;
  viewer: HTMLDivElement;
  thumbnails: HTMLDivElement;
  pdfUrl: string;
  documentId: string;
  versionId: string;
  initialPage: number;
  handlers: PdfControllerHandlers;
}

export interface PdfReaderController {
  mount(options: PdfControllerMountOptions): Promise<void>;
  destroy(): void;
  goToPage(page: number, origin?: PageChangeOrigin): void;
  previousPage(): void;
  nextPage(): void;
  zoomIn(): void;
  zoomOut(): void;
  setScaleMode(mode: ScaleMode): void;
  rotateClockwise(): void;
  rotateCounterclockwise(): void;
  retryPage(page: number): void;
  setVisualAnnotations(annotations: readonly VisualAnnotationRenderItem[]): void;
  canonicalizeSelection(
    pdfPage: number,
    normalizedViewportRects: readonly NormalizedVisualRect[],
  ): NormalizedVisualRect[] | null;
  focusVisualAnnotation(annotationId: string): void;
  search(query: string, direction: SearchDirection, options: SearchOptions, again: boolean): void;
  clearSelection(reason?: SelectionClearReason): void;
}

export type PdfReaderControllerFactory = () => PdfReaderController;
