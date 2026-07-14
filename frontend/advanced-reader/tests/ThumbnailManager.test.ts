import { waitFor } from "@testing-library/react";
import type { PDFDocumentProxy, PDFPageProxy, RenderTask } from "pdfjs-dist";
import type { EventBus } from "pdfjs-dist/web/pdf_viewer.mjs";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ThumbnailManager } from "../src/pdf/ThumbnailManager";

vi.mock("pdfjs-dist", () => ({
  AnnotationMode: { DISABLE: 0 },
}));

type PaintFixture = "blank" | "painted";

interface ControlledRenderTask {
  task: RenderTask;
  cancel: ReturnType<typeof vi.fn>;
  resolve: () => void;
  reject: (reason: Error) => void;
}

interface RenderStep {
  paint: PaintFixture;
  controlled: ControlledRenderTask;
}

interface ThumbnailHarness {
  container: HTMLDivElement;
  dispatch: ReturnType<typeof vi.fn>;
  getPage: ReturnType<typeof vi.fn>;
  getViewport: ReturnType<typeof vi.fn>;
  manager: ThumbnailManager;
  onSelect: ReturnType<typeof vi.fn>;
  render: ReturnType<typeof vi.fn>;
}

interface Deferred<T> {
  promise: Promise<T>;
  resolve(value: T): void;
}

const originalIntersectionObserver = Object.getOwnPropertyDescriptor(
  window,
  "IntersectionObserver",
);
const originalDevicePixelRatio = Object.getOwnPropertyDescriptor(window, "devicePixelRatio");

function restoreWindowProperty(name: string, descriptor: PropertyDescriptor | undefined): void {
  if (descriptor === undefined) {
    Reflect.deleteProperty(window, name);
  } else {
    Object.defineProperty(window, name, descriptor);
  }
}

function controlledRenderTask(settled = false): ControlledRenderTask {
  let resolvePromise: () => void = () => undefined;
  let rejectPromise: (reason: Error) => void = () => undefined;
  const promise = new Promise<void>((resolve, reject) => {
    resolvePromise = resolve;
    rejectPromise = reject;
  });
  const cancel = vi.fn(() => {
    const reason = new Error("Rendering cancelled by test fixture.");
    reason.name = "RenderingCancelledException";
    rejectPromise(reason);
  });
  const controlled = {
    task: { promise, cancel } as unknown as RenderTask,
    cancel,
    resolve: resolvePromise,
    reject: rejectPromise,
  };
  if (settled) resolvePromise();
  return controlled;
}

function deferred<T>(): Deferred<T> {
  let resolvePromise!: (value: T) => void;
  const promise = new Promise<T>((resolve) => {
    resolvePromise = resolve;
  });
  return { promise, resolve: resolvePromise };
}

function installIntersectionObserver(): (targets: Element[], isIntersecting?: boolean) => void {
  let callback: IntersectionObserverCallback | null = null;
  class FixtureIntersectionObserver {
    constructor(value: IntersectionObserverCallback) {
      callback = value;
    }

    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  }
  Object.defineProperty(window, "IntersectionObserver", {
    configurable: true,
    value: FixtureIntersectionObserver,
  });
  return (targets, isIntersecting = true) => {
    if (callback === null) throw new Error("IntersectionObserver fixture was not constructed.");
    callback(
      targets.map((target) => ({ isIntersecting, target }) as IntersectionObserverEntry),
      {} as IntersectionObserver,
    );
  };
}

function installCanvasContexts(): void {
  const contexts = new WeakMap<HTMLCanvasElement, CanvasRenderingContext2D>();
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(function getContext(
    this: HTMLCanvasElement,
  ) {
    const existing = contexts.get(this);
    if (existing !== undefined) return existing;

    let drawnCanvas: HTMLCanvasElement | null = null;
    const context = {
      drawImage: vi.fn((source: CanvasImageSource) => {
        drawnCanvas = source instanceof HTMLCanvasElement ? source : null;
      }),
      getImageData: vi.fn((_x: number, _y: number, width: number, height: number) => {
        const pixels = new Uint8ClampedArray(width * height * 4);
        pixels.fill(255);
        if (drawnCanvas?.dataset.paintFixture === "painted") {
          pixels[0] = 18;
          pixels[1] = 72;
          pixels[2] = 140;
        }
        return { data: pixels };
      }),
    } as unknown as CanvasRenderingContext2D;
    contexts.set(this, context);
    return context;
  });
}

function createHarness(steps: RenderStep[]): ThumbnailHarness {
  let renderIndex = 0;
  const getViewport = vi.fn(({ scale, rotation = 0 }: { scale: number; rotation?: number }) => {
    const quarterTurn = Math.abs(rotation) % 180 === 90;
    return {
      width: (quarterTurn ? 800 : 600) * scale,
      height: (quarterTurn ? 600 : 800) * scale,
      rotation,
      scale,
    };
  });
  const render = vi.fn((parameters: { canvas: HTMLCanvasElement }) => {
    const step = steps[renderIndex];
    if (step === undefined) throw new Error("Missing RenderTask fixture.");
    renderIndex += 1;
    parameters.canvas.dataset.paintFixture = step.paint;
    return step.controlled.task;
  });
  const pdfPage = { getViewport, render } as unknown as PDFPageProxy;
  const getPage = vi.fn().mockResolvedValue(pdfPage);
  const pdfDocument = { numPages: 1, getPage } as unknown as PDFDocumentProxy;
  const dispatch = vi.fn();
  const eventBus = { dispatch } as unknown as EventBus;
  const onSelect = vi.fn();
  const scroll = document.createElement("div");
  const container = document.createElement("div");
  scroll.append(container);
  document.body.append(scroll);
  const manager = new ThumbnailManager(container, pdfDocument, onSelect, eventBus);
  return { container, dispatch, getPage, getViewport, manager, onSelect, render };
}

function thumbnail(container: HTMLDivElement): HTMLButtonElement {
  const button = container.querySelector(".thumbnail-button");
  if (!(button instanceof HTMLButtonElement)) throw new Error("Thumbnail fixture is missing.");
  return button;
}

beforeEach(() => {
  document.body.replaceChildren();
  Reflect.deleteProperty(window, "IntersectionObserver");
  Object.defineProperty(window, "devicePixelRatio", { configurable: true, value: 1 });
  installCanvasContexts();
});

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
  restoreWindowProperty("IntersectionObserver", originalIntersectionObserver);
  restoreWindowProperty("devicePixelRatio", originalDevicePixelRatio);
});

describe("ThumbnailManager rendering lifecycle", () => {
  it("renders a painted thumbnail with bounded canvas dimensions", async () => {
    const step = { paint: "painted", controlled: controlledRenderTask(true) } satisfies RenderStep;
    const harness = createHarness([step]);

    harness.manager.mount();

    await waitFor(() => expect(thumbnail(harness.container).dataset.rendered).toBe("true"));
    const button = thumbnail(harness.container);
    const canvas = button.querySelector("canvas");
    expect(canvas).toBeInstanceOf(HTMLCanvasElement);
    expect(canvas).toHaveAttribute("width", "132");
    expect(canvas).toHaveAttribute("height", "176");
    expect(canvas).toHaveStyle({ width: "132px", height: "176px" });
    expect(button.dataset.renderError).toBeUndefined();
    expect(harness.render).toHaveBeenCalledTimes(1);
    expect(harness.dispatch).toHaveBeenCalledWith(
      "thumbnailrendered",
      expect.objectContaining({ pageNumber: 1, error: null }),
    );

    harness.manager.destroy();
  });

  it("shows a blank-canvas error and retries visibly on click", async () => {
    const blank = { paint: "blank", controlled: controlledRenderTask(true) } satisfies RenderStep;
    const painted = { paint: "painted", controlled: controlledRenderTask(true) } satisfies RenderStep;
    const harness = createHarness([blank, painted]);

    harness.manager.mount();
    await waitFor(() => expect(thumbnail(harness.container).dataset.renderError).toBe("true"));

    const button = thumbnail(harness.container);
    expect(button).not.toHaveAttribute("data-rendered");
    expect(button.querySelector(".thumbnail-render-error")).toHaveTextContent(
      "No renderizada · reintentar",
    );
    expect(harness.dispatch).toHaveBeenCalledWith(
      "thumbnailrendered",
      expect.objectContaining({ pageNumber: 1, error: "page_render_failed" }),
    );

    button.click();
    await waitFor(() => expect(button.dataset.rendered).toBe("true"));

    expect(button.dataset.renderError).toBeUndefined();
    expect(button.querySelector(".thumbnail-render-error")).toBeNull();
    expect(harness.render).toHaveBeenCalledTimes(2);
    expect(harness.onSelect).toHaveBeenCalledWith(1);
    expect(harness.dispatch).toHaveBeenLastCalledWith(
      "thumbnailrendered",
      expect.objectContaining({ pageNumber: 1, error: null }),
    );

    harness.manager.destroy();
  });

  it("cancels an in-flight task and re-renders the current thumbnail after rotation", async () => {
    const initial = { paint: "painted", controlled: controlledRenderTask() } satisfies RenderStep;
    const rotated = { paint: "painted", controlled: controlledRenderTask(true) } satisfies RenderStep;
    const harness = createHarness([initial, rotated]);

    harness.manager.mount();
    await waitFor(() => expect(harness.render).toHaveBeenCalledTimes(1));
    harness.manager.setCurrent(1);
    harness.manager.setRotation(90);

    await waitFor(() => expect(harness.render).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(thumbnail(harness.container).dataset.rendered).toBe("true"));

    expect(initial.controlled.cancel).toHaveBeenCalledTimes(1);
    const rotatedParameters = harness.render.mock.calls[1]?.[0] as {
      canvas: HTMLCanvasElement;
      viewport: { height: number; rotation: number; width: number };
    };
    expect(rotatedParameters.viewport).toMatchObject({ width: 132, height: 99, rotation: 90 });
    expect(rotatedParameters.canvas).toHaveAttribute("width", "132");
    expect(rotatedParameters.canvas).toHaveAttribute("height", "99");
    expect(harness.getViewport).toHaveBeenCalledWith({ scale: 1, rotation: 90 });

    harness.manager.destroy();
  });

  it("restarts every visible thumbnail after rotation without stale getPage cleanup", async () => {
    const triggerIntersection = installIntersectionObserver();
    const oldPageOne = deferred<PDFPageProxy>();
    const oldPageTwo = deferred<PDFPageProxy>();
    const getViewport = vi.fn(({ scale, rotation = 0 }: { scale: number; rotation?: number }) => ({
      width: (Math.abs(rotation) % 180 === 90 ? 800 : 600) * scale,
      height: (Math.abs(rotation) % 180 === 90 ? 600 : 800) * scale,
      rotation,
      scale,
    }));
    const render = vi.fn((parameters: { canvas: HTMLCanvasElement }) => {
      parameters.canvas.dataset.paintFixture = "painted";
      return controlledRenderTask(true).task;
    });
    const pageProxy = { getViewport, render } as unknown as PDFPageProxy;
    const getPage = vi.fn()
      .mockReturnValueOnce(oldPageOne.promise)
      .mockReturnValueOnce(oldPageTwo.promise)
      .mockResolvedValue(pageProxy);
    const pdfDocument = { numPages: 2, getPage } as unknown as PDFDocumentProxy;
    const dispatch = vi.fn();
    const container = document.createElement("div");
    const scroll = document.createElement("div");
    scroll.append(container);
    document.body.append(scroll);
    const manager = new ThumbnailManager(
      container,
      pdfDocument,
      vi.fn(),
      { dispatch } as unknown as EventBus,
    );

    manager.mount();
    const buttons = [...container.querySelectorAll<HTMLButtonElement>(".thumbnail-button")];
    triggerIntersection(buttons);
    await waitFor(() => expect(getPage).toHaveBeenCalledTimes(2));

    manager.setRotation(90);
    await waitFor(() => expect(getPage).toHaveBeenCalledTimes(4));
    await waitFor(() =>
      expect(buttons.map((button) => button.dataset.rendered)).toEqual(["true", "true"]),
    );

    oldPageOne.resolve(pageProxy);
    oldPageTwo.resolve(pageProxy);
    await waitFor(() => expect(render).toHaveBeenCalledTimes(2));
    expect(buttons.map((button) => button.dataset.rendering)).toEqual([undefined, undefined]);
    expect(buttons.map((button) => button.dataset.rendered)).toEqual(["true", "true"]);
    expect(dispatch).toHaveBeenCalledTimes(2);

    triggerIntersection([buttons[1]], false);
    manager.setRotation(180);
    await waitFor(() => expect(getPage).toHaveBeenCalledTimes(5));
    await waitFor(() => expect(render).toHaveBeenCalledTimes(3));
    expect(buttons[0]?.dataset.rendered).toBe("true");
    expect(buttons[1]?.dataset.rendered).toBeUndefined();

    manager.destroy();
  });

  it("cancels active rendering and removes thumbnail DOM during cleanup", async () => {
    const pending = { paint: "painted", controlled: controlledRenderTask() } satisfies RenderStep;
    const harness = createHarness([pending]);

    harness.manager.mount();
    await waitFor(() => expect(harness.render).toHaveBeenCalledTimes(1));

    harness.manager.destroy();
    await waitFor(() => expect(pending.controlled.cancel).toHaveBeenCalledTimes(1));

    expect(harness.container).toBeEmptyDOMElement();
    expect(harness.dispatch).not.toHaveBeenCalled();
  });
});
