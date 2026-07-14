import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const pdfJsMocks = vi.hoisted(() => ({
  eventBuses: [] as unknown[],
  findControllers: [] as unknown[],
  getDocument: vi.fn(),
  globalWorkerOptions: { workerSrc: "" },
  inspectCanvasPaint: vi.fn(),
  linkServices: [] as unknown[],
  thumbnailManagers: [] as unknown[],
  viewers: [] as unknown[],
}));

vi.mock("pdfjs-dist", () => ({
  AnnotationEditorType: { NONE: 0 },
  AnnotationMode: { ENABLE: 1 },
  GlobalWorkerOptions: pdfJsMocks.globalWorkerOptions,
  getDocument: pdfJsMocks.getDocument,
}));

vi.mock("pdfjs-dist/web/pdf_viewer.mjs", () => {
  interface ListenerOptions {
    once?: boolean;
    signal?: AbortSignal;
  }

  interface ListenerEntry {
    listener: (event: unknown) => void;
    once: boolean;
  }

  class EventBus {
    readonly listeners = new Map<string, Set<ListenerEntry>>();

    constructor() {
      pdfJsMocks.eventBuses.push(this);
    }

    on(
      eventName: string,
      listener: (event: unknown) => void,
      options: ListenerOptions = {},
    ): void {
      if (options.signal?.aborted) return;
      const entries = this.listeners.get(eventName) ?? new Set<ListenerEntry>();
      const entry = { listener, once: options.once === true };
      entries.add(entry);
      this.listeners.set(eventName, entries);
      options.signal?.addEventListener(
        "abort",
        () => {
          entries.delete(entry);
        },
        { once: true },
      );
    }

    dispatch(eventName: string, event: unknown): void {
      const entries = this.listeners.get(eventName);
      if (entries === undefined) return;
      for (const entry of [...entries]) {
        entry.listener(event);
        if (entry.once) entries.delete(entry);
      }
    }
  }

  class PDFLinkService {
    externalLinkEnabled = true;
    readonly setDocument = vi.fn();
    readonly setViewer = vi.fn();

    constructor(_options: unknown) {
      pdfJsMocks.linkServices.push(this);
    }
  }

  class PDFFindController {
    constructor(_options: unknown) {
      pdfJsMocks.findControllers.push(this);
    }
  }

  class PDFRenderingQueue {
    readonly renderHighestPriority = vi.fn();
    readonly setViewer = vi.fn();
  }

  class PDFViewer {
    currentPageNumber = 1;
    currentScale = 1;
    currentScaleValue = "page-width";
    pagesRotation = 0;
    readonly forceRendering = vi.fn(() => true);
    readonly nextPage = vi.fn(() => false);
    readonly previousPage = vi.fn(() => false);
    readonly setDocument = vi.fn();
    readonly update = vi.fn();
    readonly pageView: {
      div: HTMLDivElement;
      reset: ReturnType<typeof vi.fn>;
    };

    constructor(options: { viewer: HTMLDivElement }) {
      const page = document.createElement("div");
      page.className = "page";
      const canvasWrapper = document.createElement("div");
      canvasWrapper.className = "canvasWrapper";
      const canvas = document.createElement("canvas");
      canvas.width = 128;
      canvas.height = 192;
      canvasWrapper.append(canvas);
      page.append(canvasWrapper);
      options.viewer.append(page);
      this.pageView = { div: page, reset: vi.fn() };
      pdfJsMocks.viewers.push(this);
    }

    getPageView(pageIndex: number): typeof this.pageView | undefined {
      return pageIndex === 0 ? this.pageView : undefined;
    }
  }

  return {
    EventBus,
    FindState: { FOUND: 0, PENDING: 1, NOT_FOUND: 2, WRAPPED: 3 },
    LinkTarget: { NONE: 0 },
    PDFFindController,
    PDFLinkService,
    PDFRenderingQueue,
    PDFViewer,
  };
});

vi.mock("../generated/pdf.worker.min.mjs?url", () => ({
  default: "/assets/pdf.worker.min.mjs",
}));

vi.mock("../src/pdf/ThumbnailManager", () => {
  class ThumbnailManager {
    readonly destroy = vi.fn();
    readonly mount = vi.fn();
    readonly setCurrent = vi.fn();
    readonly setRotation = vi.fn();

    constructor(..._args: unknown[]) {
      pdfJsMocks.thumbnailManagers.push(this);
    }
  }

  return { ThumbnailManager };
});

vi.mock("../src/pdf/canvasPaint", () => ({
  inspectCanvasPaint: pdfJsMocks.inspectCanvasPaint,
}));

import {
  PDFJS_RESOURCE_URLS,
  PDFJS_VERSION,
  PdfJsController,
} from "../src/pdf/PdfJsController";
import type {
  PdfControllerHandlers,
  PdfControllerMountOptions,
} from "../src/pdf/types";

interface FakePdfDocument {
  numPages: number;
}

interface LoadingTask {
  destroy: ReturnType<typeof vi.fn>;
  promise: Promise<FakePdfDocument>;
}

interface Deferred<T> {
  promise: Promise<T>;
  resolve(value: T): void;
}

interface MockEventBus {
  dispatch(eventName: string, event: unknown): void;
}

interface MockViewer {
  currentPageNumber: number;
  forceRendering: ReturnType<typeof vi.fn>;
  pageView: {
    div: HTMLDivElement;
    reset: ReturnType<typeof vi.fn>;
  };
  setDocument: ReturnType<typeof vi.fn>;
  update: ReturnType<typeof vi.fn>;
}

const controllers: PdfJsController[] = [];

function deferred<T>(): Deferred<T> {
  let resolvePromise!: (value: T) => void;
  const promise = new Promise<T>((resolve) => {
    resolvePromise = resolve;
  });
  return { promise, resolve: resolvePromise };
}

function loadingTask(promise: Promise<FakePdfDocument>): LoadingTask {
  return {
    destroy: vi.fn().mockResolvedValue(undefined),
    promise,
  };
}

function handlers(): PdfControllerHandlers {
  return {
    onError: vi.fn(),
    onPageChanged: vi.fn(),
    onPageRendered: vi.fn(),
    onPageRenderFailed: vi.fn(),
    onReady: vi.fn(),
    onRotationChanged: vi.fn(),
    onSearchChanged: vi.fn(),
    onSelectionChanged: vi.fn(),
    onZoomChanged: vi.fn(),
  };
}

function mountOptions(overrides: Partial<PdfControllerMountOptions> = {}): PdfControllerMountOptions {
  const container = document.createElement("div");
  const viewer = document.createElement("div");
  const thumbnails = document.createElement("div");
  container.append(viewer);
  document.body.append(container, thumbnails);
  return {
    container,
    documentId: "doc_123e4567-e89b-42d3-a456-426614174000",
    handlers: handlers(),
    initialPage: 1,
    pdfUrl: "/api/advanced-reader/documents/doc_123e4567-e89b-42d3-a456-426614174000/pdf",
    thumbnails,
    versionId: "dver_123e4567-e89b-42d3-a456-426614174001",
    viewer,
    ...overrides,
  };
}

function eventBus(index = pdfJsMocks.eventBuses.length - 1): MockEventBus {
  return pdfJsMocks.eventBuses[index] as MockEventBus;
}

function viewer(index = pdfJsMocks.viewers.length - 1): MockViewer {
  return pdfJsMocks.viewers[index] as MockViewer;
}

async function waitForDocument(view: MockViewer, document: FakePdfDocument): Promise<void> {
  await vi.waitFor(() => {
    expect(view.setDocument).toHaveBeenCalledWith(document);
  });
}

async function mountReady(
  controller: PdfJsController,
  options: PdfControllerMountOptions,
  document: FakePdfDocument = { numPages: 3 },
): Promise<{ bus: MockEventBus; task: LoadingTask; view: MockViewer }> {
  const task = loadingTask(Promise.resolve(document));
  pdfJsMocks.getDocument.mockReturnValueOnce(task);
  const mountPromise = controller.mount(options);
  const bus = eventBus();
  const view = viewer();
  await waitForDocument(view, document);
  bus.dispatch("pagesinit", { source: view });
  await mountPromise;
  return { bus, task, view };
}

beforeEach(() => {
  pdfJsMocks.eventBuses.length = 0;
  pdfJsMocks.findControllers.length = 0;
  pdfJsMocks.linkServices.length = 0;
  pdfJsMocks.thumbnailManagers.length = 0;
  pdfJsMocks.viewers.length = 0;
  pdfJsMocks.getDocument.mockReset();
  pdfJsMocks.inspectCanvasPaint.mockReset();
  pdfJsMocks.inspectCanvasPaint.mockReturnValue({
    height: 192,
    maxChannel: 255,
    minChannel: 0,
    nonWhitePixels: 48,
    painted: true,
    sampledPixels: 128 * 192,
    width: 128,
  });
});

afterEach(() => {
  for (const controller of controllers.splice(0)) controller.destroy();
  document.body.replaceChildren();
});

function controller(): PdfJsController {
  const instance = new PdfJsController();
  controllers.push(instance);
  return instance;
}

describe("PdfJsController", () => {
  it("uses the pinned PDF.js version, same-origin worker, and local resource URLs", async () => {
    const instance = controller();
    const options = mountOptions();

    await mountReady(instance, options);

    expect(PDFJS_VERSION).toBe("6.1.200");
    expect(pdfJsMocks.globalWorkerOptions.workerSrc).toBe("/assets/pdf.worker.min.mjs");
    expect(pdfJsMocks.globalWorkerOptions.workerSrc).not.toMatch(/^https?:/u);
    expect(PDFJS_RESOURCE_URLS).toEqual({
      cMapUrl: "/assets/pdfjs-6.1.200/cmaps/",
      iccUrl: "/assets/pdfjs-6.1.200/iccs/",
      standardFontDataUrl: "/assets/pdfjs-6.1.200/standard_fonts/",
      wasmUrl: "/assets/pdfjs-6.1.200/wasm/",
    });
    expect(pdfJsMocks.getDocument).toHaveBeenCalledWith(
      expect.objectContaining({
        ...PDFJS_RESOURCE_URLS,
        url: options.pdfUrl,
      }),
    );
    for (const resourceUrl of Object.values(PDFJS_RESOURCE_URLS)) {
      expect(resourceUrl).toMatch(/^\/assets\/pdfjs-6\.1\.200\//u);
      expect(resourceUrl).not.toMatch(/^https?:/u);
    }
  });

  it("sets each active PDF document exactly once", async () => {
    const instance = controller();
    const firstDocument = { numPages: 3 };
    const first = await mountReady(instance, mountOptions(), firstDocument);

    expect(first.view.setDocument.mock.calls.filter(([value]) => value === firstDocument)).toHaveLength(1);

    const secondDocument = { numPages: 5 };
    const secondTask = loadingTask(Promise.resolve(secondDocument));
    pdfJsMocks.getDocument.mockReturnValueOnce(secondTask);
    const secondMount = instance.mount(mountOptions());
    const secondBus = eventBus();
    const secondView = viewer();
    await waitForDocument(secondView, secondDocument);
    secondBus.dispatch("pagesinit", { source: secondView });
    await secondMount;

    expect(first.view.setDocument.mock.calls.filter(([value]) => value === firstDocument)).toHaveLength(1);
    expect(secondView.setDocument.mock.calls.filter(([value]) => value === secondDocument)).toHaveLength(1);
  });

  it("reports a page only after pagesinit and its first painted pagerendered event", async () => {
    const instance = controller();
    const options = mountOptions();
    const document = { numPages: 3 };
    const task = loadingTask(Promise.resolve(document));
    pdfJsMocks.getDocument.mockReturnValueOnce(task);

    const mountPromise = instance.mount(options);
    const bus = eventBus();
    const view = viewer();
    await waitForDocument(view, document);
    expect(options.handlers.onReady).not.toHaveBeenCalled();
    expect(options.handlers.onPageRendered).not.toHaveBeenCalled();

    bus.dispatch("pagesinit", { source: view });
    await mountPromise;
    expect(options.handlers.onReady).toHaveBeenCalledOnce();
    expect(options.handlers.onPageRendered).not.toHaveBeenCalled();

    bus.dispatch("pagerendered", { pageNumber: 1, source: view });
    expect(pdfJsMocks.inspectCanvasPaint).toHaveBeenCalledWith(
      view.pageView.div.querySelector("canvas"),
    );
    expect(options.handlers.onPageRendered).toHaveBeenCalledOnce();
    expect(options.handlers.onPageRendered).toHaveBeenCalledWith(1);
  });

  it("does not let a stale StrictMode mount destroy or initialize the replacement", async () => {
    const instance = controller();
    const firstDeferred = deferred<FakePdfDocument>();
    const secondDeferred = deferred<FakePdfDocument>();
    const firstTask = loadingTask(firstDeferred.promise);
    const secondTask = loadingTask(secondDeferred.promise);
    pdfJsMocks.getDocument.mockReturnValueOnce(firstTask).mockReturnValueOnce(secondTask);

    const firstMount = instance.mount(mountOptions());
    const firstView = viewer();
    const secondMount = instance.mount(mountOptions());
    const secondBus = eventBus();
    const secondView = viewer();

    expect(firstTask.destroy).toHaveBeenCalledOnce();
    expect(secondTask.destroy).not.toHaveBeenCalled();
    firstDeferred.resolve({ numPages: 2 });
    await firstMount;
    expect(firstView.setDocument).not.toHaveBeenCalledWith(expect.objectContaining({ numPages: 2 }));
    expect(secondView.setDocument).not.toHaveBeenCalled();
    expect(secondTask.destroy).not.toHaveBeenCalled();

    const activeDocument = { numPages: 7 };
    secondDeferred.resolve(activeDocument);
    await waitForDocument(secondView, activeDocument);
    secondBus.dispatch("pagesinit", { source: secondView });
    await secondMount;

    expect(secondView.setDocument.mock.calls.filter(([value]) => value === activeDocument)).toHaveLength(1);
    expect(secondTask.destroy).not.toHaveBeenCalled();
  });

  it("settles cleanup after setDocument even when pagesinit never arrives", async () => {
    const instance = controller();
    const options = mountOptions();
    const document = { numPages: 3 };
    const task = loadingTask(Promise.resolve(document));
    pdfJsMocks.getDocument.mockReturnValueOnce(task);

    const mountPromise = instance.mount(options);
    const view = viewer();
    await waitForDocument(view, document);
    instance.destroy();

    await expect(mountPromise).resolves.toBeUndefined();
    expect(task.destroy).toHaveBeenCalledOnce();
    expect(view.setDocument).toHaveBeenCalledWith(null);
    expect(options.handlers.onReady).not.toHaveBeenCalled();
  });

  it("cancels only the unmounted loading task during replacement and final cleanup", async () => {
    const instance = controller();
    const first = await mountReady(instance, mountOptions());
    const secondDocument = { numPages: 4 };
    const secondTask = loadingTask(Promise.resolve(secondDocument));
    pdfJsMocks.getDocument.mockReturnValueOnce(secondTask);

    const secondMount = instance.mount(mountOptions());
    const secondBus = eventBus();
    const secondView = viewer();
    await waitForDocument(secondView, secondDocument);
    secondBus.dispatch("pagesinit", { source: secondView });
    await secondMount;

    expect(first.task.destroy).toHaveBeenCalledOnce();
    expect(secondTask.destroy).not.toHaveBeenCalled();
    instance.destroy();
    expect(first.task.destroy).toHaveBeenCalledOnce();
    expect(secondTask.destroy).toHaveBeenCalledOnce();
    expect(secondView.setDocument).toHaveBeenCalledWith(null);
  });

  it("surfaces a blank canvas and retries it through reset, update, and forceRendering", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const instance = controller();
    const options = mountOptions();
    const mounted = await mountReady(instance, options);
    const canvas = mounted.view.pageView.div.querySelector("canvas");
    expect(canvas).toBeInstanceOf(HTMLCanvasElement);
    if (!(canvas instanceof HTMLCanvasElement)) throw new Error("Expected the page canvas fixture.");
    canvas.width = 0;
    canvas.height = 0;
    pdfJsMocks.inspectCanvasPaint.mockReturnValue({
      height: 0,
      maxChannel: 0,
      minChannel: 255,
      nonWhitePixels: 0,
      painted: false,
      sampledPixels: 0,
      width: 0,
    });

    mounted.bus.dispatch("pagerendered", { pageNumber: 1, source: mounted.view });
    mounted.bus.dispatch("pagerendered", { pageNumber: 1, source: mounted.view });

    expect(options.handlers.onPageRendered).not.toHaveBeenCalled();
    expect(options.handlers.onPageRenderFailed).toHaveBeenCalledOnce();
    expect(options.handlers.onPageRenderFailed).toHaveBeenCalledWith(1);
    const error = mounted.view.pageView.div.querySelector<HTMLElement>(
      '[data-error-code="page_render_failed"]',
    );
    expect(error).toHaveAttribute("role", "alert");
    expect(mounted.view.pageView.div).toHaveClass("has-render-error");

    instance.retryPage(1);

    expect(mounted.view.pageView.reset).toHaveBeenCalledOnce();
    expect(mounted.view.update).toHaveBeenCalledOnce();
    expect(mounted.view.forceRendering).toHaveBeenCalledOnce();
    expect(mounted.view.pageView.div).not.toHaveClass("has-render-error");
    expect(mounted.view.pageView.div.querySelector('[data-error-code="page_render_failed"]')).toBeNull();

    canvas.width = 128;
    canvas.height = 192;
    pdfJsMocks.inspectCanvasPaint.mockReturnValue({
      height: 192,
      maxChannel: 255,
      minChannel: 0,
      nonWhitePixels: 48,
      painted: true,
      sampledPixels: 128 * 192,
      width: 128,
    });
    mounted.bus.dispatch("pagerendered", { pageNumber: 1, source: mounted.view });
    expect(options.handlers.onPageRendered).toHaveBeenCalledWith(1);
  });

  it("reports a pagerendered event whose PageView is unavailable", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const instance = controller();
    const options = mountOptions();
    const mounted = await mountReady(instance, options);

    mounted.bus.dispatch("pagerendered", { pageNumber: 2, source: mounted.view });
    mounted.bus.dispatch("pagerendered", { pageNumber: 2, source: mounted.view });

    expect(options.handlers.onPageRendered).not.toHaveBeenCalled();
    expect(options.handlers.onPageRenderFailed).toHaveBeenCalledOnce();
    expect(options.handlers.onPageRenderFailed).toHaveBeenCalledWith(2);
  });
});
