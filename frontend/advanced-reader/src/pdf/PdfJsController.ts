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
import { inspectCanvasPaint } from "./canvasPaint";
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

export const PDFJS_VERSION = "6.1.200";
export const PDFJS_RESOURCE_BASE_URL = `/assets/pdfjs-${PDFJS_VERSION}`;
export const PDFJS_RESOURCE_URLS = Object.freeze({
  cMapUrl: `${PDFJS_RESOURCE_BASE_URL}/cmaps/`,
  standardFontDataUrl: `${PDFJS_RESOURCE_BASE_URL}/standard_fonts/`,
  wasmUrl: `${PDFJS_RESOURCE_BASE_URL}/wasm/`,
  iccUrl: `${PDFJS_RESOURCE_BASE_URL}/iccs/`,
});

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
  pageNumber: number;
}

interface PageRenderEvent {
  pageNumber: number;
  cssTransform?: boolean;
  isDetailView?: boolean;
  error?: unknown;
}

interface RetryablePageView {
  div: HTMLDivElement;
  reset(): void;
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
  readonly #failedPages = new Set<number>();

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
    const viewerOptions: ConstructorParameters<typeof PDFViewer>[0] & {
      abortSignal: AbortSignal;
    } = {
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
      abortSignal: abortController.signal,
    };
    const viewer = new PDFViewer(viewerOptions);
    linkService.setViewer(viewer);
    this.#eventBus = eventBus;
    this.#viewer = viewer;

    const pagesInitialized = new Promise<void>((resolve) => {
      const settle = () => {
        abortController.signal.removeEventListener("abort", settle);
        resolve();
      };
      abortController.signal.addEventListener("abort", settle, { once: true });
      eventBus.on("pagesinit", settle, {
        once: true,
        signal: abortController.signal,
      });
    });

    eventBus.on(
      "pagerender",
      ({ pageNumber }: PageRenderEvent) => {
        this.#clearPageError(pageNumber);
      },
      { signal: abortController.signal },
    );
    eventBus.on(
      "pagerendered",
      ({ pageNumber, error, isDetailView }: PageRenderEvent) => {
        if (isDetailView) return;
        const pageView = viewer.getPageView(pageNumber - 1) as RetryablePageView | undefined;
        if (pageView === undefined) {
          this.#reportPageFailure(pageNumber);
          return;
        }
        const canvas = pageView?.div.querySelector(".canvasWrapper canvas");
        const paint =
          canvas instanceof HTMLCanvasElement ? inspectCanvasPaint(canvas) : null;
        if (error || paint?.painted !== true) {
          this.#reportPageFailure(pageNumber);
          return;
        }
        this.#failedPages.delete(pageNumber);
        this.#clearPageError(pageNumber);
        pageView.div.dataset.renderStatus = "painted";
        this.#handlers?.onPageRendered(pageNumber);
      },
      { signal: abortController.signal },
    );
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
      ({ pagesRotation, pageNumber }: RotationChangingEvent) => {
        this.clearSelection("rotation_change");
        viewer.currentPageNumber = pageNumber;
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
        ...PDFJS_RESOURCE_URLS,
        cMapPacked: true,
        withCredentials: false,
        isEvalSupported: false,
        useWasm: false,
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
      linkService.setDocument(pdfDocument, null);
      viewer.setDocument(pdfDocument);
      const thumbnails = new ThumbnailManager(
        options.thumbnails,
        pdfDocument,
        (page) => this.goToPage(page, "thumbnail"),
        eventBus,
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
    this.#failedPages.clear();
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

  retryPage(page: number): void {
    if (this.#viewer === null || this.#pdfDocument === null) return;
    const target = safePage(page, this.#pdfDocument.numPages);
    const pageView = this.#viewer.getPageView(target - 1) as RetryablePageView | undefined;
    if (pageView === undefined) return;
    this.#failedPages.delete(target);
    this.#clearPageError(target);
    pageView.reset();
    this.#viewer.currentPageNumber = target;
    this.#viewer.update();
    this.#viewer.forceRendering(undefined);
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

  #pageView(pageNumber: number): RetryablePageView | null {
    const view = this.#viewer?.getPageView(pageNumber - 1) as RetryablePageView | undefined;
    return view?.div instanceof HTMLDivElement ? view : null;
  }

  #clearPageError(pageNumber: number): void {
    const page = this.#pageView(pageNumber)?.div;
    if (page === undefined) return;
    page.classList.remove("has-render-error");
    delete page.dataset.renderStatus;
    page.querySelector(":scope > .page-render-error")?.remove();
  }

  #reportPageFailure(pageNumber: number): void {
    const page = this.#pageView(pageNumber)?.div;
    if (page !== undefined) {
      page.dataset.renderStatus = "failed";
      page.classList.add("has-render-error");
      if (page.querySelector(":scope > .page-render-error") === null) {
        const error = document.createElement("div");
        error.className = "page-render-error";
        error.dataset.errorCode = "page_render_failed";
        error.setAttribute("role", "alert");
        const message = document.createElement("p");
        message.textContent = `No se pudo renderizar PDF page ${pageNumber}.`;
        const retry = document.createElement("button");
        retry.type = "button";
        retry.textContent = "Reintentar página";
        retry.addEventListener("click", () => this.retryPage(pageNumber), {
          signal: this.#abortController?.signal,
        });
        error.append(message, retry);
        page.append(error);
      }
    }
    if (!this.#failedPages.has(pageNumber)) {
      this.#failedPages.add(pageNumber);
      console.error(`Advanced Reader page_render_failed for PDF page ${pageNumber}.`);
      this.#handlers?.onPageRenderFailed(pageNumber);
    }
  }
}

export const createPdfJsController = (): PdfReaderController => new PdfJsController();
