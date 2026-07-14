import {
  AnnotationEditorType,
  AnnotationMode,
  GlobalWorkerOptions,
  getDocument,
} from "pdfjs-dist";
import type { PDFDocumentLoadingTask, PDFDocumentProxy } from "pdfjs-dist";
import {
  EventBus,
  FindState,
  LinkTarget,
  PDFFindController,
  PDFLinkService,
  PDFViewer,
} from "pdfjs-dist/web/pdf_viewer.mjs";
import workerUrl from "../../generated/pdf.worker.min.mjs?url";

import { captureTextSelection, clearBrowserSelection } from "../selection/captureSelection";
import type { PageChangeOrigin, SelectionClearReason } from "../types/events";
import { ThumbnailManager } from "./ThumbnailManager";
import { normalizeSearchQuery } from "./search";
import type {
  PdfControllerMountOptions,
  PdfReaderController,
  ScaleMode,
  SearchDirection,
  SearchOptions,
  SearchStatus,
  SearchUpdate,
} from "./types";

const RANGE_CHUNK_SIZE = 64 * 1024;
const MIN_APP_SCALE = 0.25;
const MAX_APP_SCALE = 5;
const SCALE_STEP = 1.1;

GlobalWorkerOptions.workerSrc = workerUrl;

interface FindEvent {
  state: number;
  matchesCount?: { current?: number; total?: number };
}

interface PageChangingEvent {
  pageNumber: number;
}

interface ScaleChangingEvent {
  scale: number;
}

interface RotationChangingEvent {
  pagesRotation: number;
}

function safePage(value: number, total: number): number {
  const integer = Number.isFinite(value) ? Math.trunc(value) : 1;
  return Math.min(total, Math.max(1, integer));
}

function findStatus(state: number): SearchStatus {
  if (state === FindState.PENDING) return "pending";
  if (state === FindState.NOT_FOUND) return "not_found";
  if (state === FindState.WRAPPED) return "wrapped";
  if (state === FindState.FOUND) return "found";
  return "idle";
}

export class PdfJsController implements PdfReaderController {
  #abortController: AbortController | null = null;
  #loadingTask: PDFDocumentLoadingTask | null = null;
  #pdfDocument: PDFDocumentProxy | null = null;
  #eventBus: EventBus | null = null;
  #viewer: PDFViewer | null = null;
  #thumbnailManager: ThumbnailManager | null = null;
  #handlers: PdfControllerMountOptions["handlers"] | null = null;
  #selectionFrame: number | null = null;
  #matches: SearchUpdate = { status: "idle", current: 0, total: 0 };
  #nextPageOrigin: PageChangeOrigin = "pdfjs";
  #rotationDirection: "clockwise" | "counterclockwise" = "clockwise";

  async mount(options: PdfControllerMountOptions): Promise<void> {
    this.destroy();
    const abortController = new AbortController();
    this.#abortController = abortController;
    this.#handlers = options.handlers;

    const eventBus = new EventBus();
    const linkService = new PDFLinkService({
      eventBus,
      externalLinkTarget: LinkTarget.NONE,
      externalLinkRel: "noopener noreferrer nofollow",
    });
    linkService.externalLinkEnabled = false;
    Object.defineProperty(linkService, "getAttachmentContent", {
      configurable: false,
      value: async () => null,
      writable: false,
    });
    const findController = new PDFFindController({ eventBus, linkService });
    const viewer = new PDFViewer({
      container: options.container,
      viewer: options.viewer,
      eventBus,
      linkService,
      findController,
      annotationMode: AnnotationMode.ENABLE,
      annotationEditorMode: AnnotationEditorType.NONE,
      enableAutoLinking: false,
      enableSelectionRendering: true,
      imagesRightClickMinSize: -1,
    });
    linkService.setViewer(viewer);
    this.#eventBus = eventBus;
    this.#viewer = viewer;

    const pagesInitialized = new Promise<void>((resolve) => {
      eventBus.on("pagesinit", () => resolve(), {
        once: true,
        signal: abortController.signal,
      });
    });

    eventBus.on(
      "pagechanging",
      ({ pageNumber }: PageChangingEvent) => {
        const origin = this.#nextPageOrigin;
        this.#nextPageOrigin = "pdfjs";
        this.clearSelection("page_change");
        this.#thumbnailManager?.setCurrent(pageNumber);
        this.#handlers?.onPageChanged(pageNumber, origin);
      },
      { signal: abortController.signal },
    );
    eventBus.on(
      "scalechanging",
      ({ scale }: ScaleChangingEvent) => {
        const boundedScale = Number.isFinite(scale)
          ? Math.min(MAX_APP_SCALE, Math.max(MIN_APP_SCALE, scale))
          : 1;
        if (boundedScale !== scale) {
          viewer.currentScale = boundedScale;
          return;
        }
        this.#handlers?.onZoomChanged(boundedScale);
      },
      { signal: abortController.signal },
    );
    eventBus.on(
      "rotationchanging",
      ({ pagesRotation }: RotationChangingEvent) => {
        this.clearSelection("rotation_change");
        this.#thumbnailManager?.setRotation(pagesRotation);
        this.#handlers?.onRotationChanged(pagesRotation, this.#rotationDirection);
      },
      { signal: abortController.signal },
    );
    const updateFind = ({ state, matchesCount }: FindEvent) => {
      this.#matches = {
        status: findStatus(state),
        current: matchesCount?.current ?? this.#matches.current,
        total: matchesCount?.total ?? this.#matches.total,
      };
      this.#handlers?.onSearchChanged(this.#matches);
    };
    eventBus.on("updatefindcontrolstate", updateFind, { signal: abortController.signal });
    eventBus.on(
      "updatefindmatchescount",
      ({ matchesCount }: FindEvent) => {
        this.#matches = {
          ...this.#matches,
          current: matchesCount?.current ?? 0,
          total: matchesCount?.total ?? 0,
        };
        this.#handlers?.onSearchChanged(this.#matches);
      },
      { signal: abortController.signal },
    );

    const captureSelection = () => {
      if (this.#selectionFrame !== null) {
        window.cancelAnimationFrame(this.#selectionFrame);
      }
      this.#selectionFrame = window.requestAnimationFrame(() => {
        this.#selectionFrame = null;
        const selection = captureTextSelection(window.getSelection(), options.viewer, {
          documentId: options.documentId,
          versionId: options.versionId,
          rotation: this.#viewer?.pagesRotation ?? 0,
          scale: this.#viewer?.currentScale ?? 1,
        });
        this.#handlers?.onSelectionChanged(selection, selection === null ? "empty" : undefined);
      });
    };
    options.viewer.addEventListener("pointerup", captureSelection, {
      signal: abortController.signal,
    });
    options.viewer.addEventListener("keyup", captureSelection, {
      signal: abortController.signal,
    });
    options.viewer.addEventListener(
      "click",
      (event) => {
        const target = event.target instanceof Element ? event.target.closest("a") : null;
        const href = target?.getAttribute("href") ?? "";
        if (href && !href.startsWith("#")) {
          event.preventDefault();
          event.stopPropagation();
        }
      },
      { capture: true, signal: abortController.signal },
    );

    try {
      const loadingTask = getDocument({
        url: options.pdfUrl,
        withCredentials: false,
        isEvalSupported: false,
        disableRange: false,
        disableStream: true,
        disableAutoFetch: true,
        rangeChunkSize: RANGE_CHUNK_SIZE,
        enableXfa: false,
        stopAtErrors: true,
      } as Parameters<typeof getDocument>[0] & { isEvalSupported: false });
      this.#loadingTask = loadingTask;
      const pdfDocument = await loadingTask.promise;
      if (abortController.signal.aborted) return;
      this.#pdfDocument = pdfDocument;
      viewer.setDocument(pdfDocument);
      linkService.setDocument(pdfDocument, null);
      const thumbnails = new ThumbnailManager(
        options.thumbnails,
        pdfDocument,
        (page) => this.goToPage(page, "thumbnail"),
      );
      this.#thumbnailManager = thumbnails;
      thumbnails.mount();
      await pagesInitialized;
      if (abortController.signal.aborted) return;
      viewer.currentScaleValue = "page-width";
      const initialPage = safePage(options.initialPage, pdfDocument.numPages);
      options.handlers.onReady(pdfDocument.numPages);
      const pageBeforeInitialization = viewer.currentPageNumber;
      this.#nextPageOrigin = "initial";
      viewer.currentPageNumber = initialPage;
      thumbnails.setCurrent(initialPage);
      if (pageBeforeInitialization === initialPage) {
        this.#nextPageOrigin = "pdfjs";
        options.handlers.onPageChanged(initialPage, "initial");
      }
      options.handlers.onZoomChanged(viewer.currentScale);
    } catch {
      if (!abortController.signal.aborted) {
        options.handlers.onError();
      }
    }
  }

  destroy(): void {
    if (this.#selectionFrame !== null) {
      window.cancelAnimationFrame(this.#selectionFrame);
      this.#selectionFrame = null;
    }
    this.#abortController?.abort();
    this.#abortController = null;
    this.#thumbnailManager?.destroy();
    this.#thumbnailManager = null;
    if (this.#viewer !== null) {
      (this.#viewer as unknown as { setDocument(document: null): void }).setDocument(null);
    }
    this.#viewer = null;
    this.#eventBus = null;
    this.#pdfDocument = null;
    if (this.#loadingTask !== null) {
      void this.#loadingTask.destroy().catch(() => undefined);
      this.#loadingTask = null;
    }
    this.#handlers = null;
    this.#matches = { status: "idle", current: 0, total: 0 };
  }

  goToPage(page: number, origin: PageChangeOrigin = "toolbar"): void {
    if (this.#viewer !== null && this.#pdfDocument !== null) {
      const target = safePage(page, this.#pdfDocument.numPages);
      if (target === this.#viewer.currentPageNumber) return;
      this.#nextPageOrigin = origin;
      this.#viewer.currentPageNumber = target;
    }
  }

  previousPage(): void {
    this.#nextPageOrigin = "toolbar";
    if (this.#viewer?.previousPage() === false) this.#nextPageOrigin = "pdfjs";
  }

  nextPage(): void {
    this.#nextPageOrigin = "toolbar";
    if (this.#viewer?.nextPage() === false) this.#nextPageOrigin = "pdfjs";
  }

  zoomIn(): void {
    if (this.#viewer !== null) {
      this.#viewer.currentScale = Math.min(MAX_APP_SCALE, this.#viewer.currentScale * SCALE_STEP);
    }
  }

  zoomOut(): void {
    if (this.#viewer !== null) {
      this.#viewer.currentScale = Math.max(MIN_APP_SCALE, this.#viewer.currentScale / SCALE_STEP);
    }
  }

  setScaleMode(mode: ScaleMode): void {
    if (this.#viewer !== null) {
      this.#viewer.currentScaleValue = mode;
    }
  }

  rotateClockwise(): void {
    if (this.#viewer !== null) {
      this.#rotationDirection = "clockwise";
      this.clearSelection("rotation_change");
      this.#viewer.pagesRotation = (this.#viewer.pagesRotation + 90) % 360;
    }
  }

  rotateCounterclockwise(): void {
    if (this.#viewer !== null) {
      this.#rotationDirection = "counterclockwise";
      this.clearSelection("rotation_change");
      this.#viewer.pagesRotation = (this.#viewer.pagesRotation + 270) % 360;
    }
  }

  search(
    query: string,
    direction: SearchDirection,
    options: SearchOptions,
    again: boolean,
  ): void {
    if (this.#eventBus === null) return;
    const boundedQuery = normalizeSearchQuery(query);
    if (!boundedQuery) {
      this.#matches = { status: "idle", current: 0, total: 0 };
      this.#handlers?.onSearchChanged(this.#matches);
      this.#eventBus.dispatch("findbarclose", { source: this });
      return;
    }
    this.#handlers?.onSearchChanged({ status: "pending", current: 0, total: 0 });
    this.#eventBus.dispatch("find", {
      source: this,
      type: again ? "again" : "",
      query: boundedQuery,
      caseSensitive: options.caseSensitive,
      entireWord: options.entireWord,
      highlightAll: true,
      findPrevious: direction === "previous",
      matchDiacritics: false,
    });
  }

  clearSelection(reason: SelectionClearReason = "user"): void {
    clearBrowserSelection();
    this.#handlers?.onSelectionChanged(null, reason);
  }
}

export const createPdfJsController = (): PdfReaderController => new PdfJsController();
