import { AnnotationMode } from "pdfjs-dist";
import type { PDFDocumentProxy, RenderTask } from "pdfjs-dist";
import type { EventBus } from "pdfjs-dist/web/pdf_viewer.mjs";

import { inspectCanvasPaint } from "./canvasPaint";

const THUMBNAIL_WIDTH = 132;
const MAX_OUTPUT_SCALE = 2;

interface ActiveRenderTask {
  generation: number;
  task: RenderTask;
}

export class ThumbnailManager {
  readonly #container: HTMLDivElement;
  readonly #document: PDFDocumentProxy;
  readonly #onSelect: (page: number) => void;
  readonly #eventBus: EventBus;
  readonly #buttons = new Map<number, HTMLButtonElement>();
  readonly #renderTasks = new Map<number, ActiveRenderTask>();
  readonly #renderingGenerations = new Map<number, number>();
  readonly #visiblePages = new Set<number>();
  readonly #abortController = new AbortController();
  #observer: IntersectionObserver | null = null;
  #rotation = 0;
  #generation = 0;
  #destroyed = false;

  constructor(
    container: HTMLDivElement,
    pdfDocument: PDFDocumentProxy,
    onSelect: (page: number) => void,
    eventBus: EventBus,
  ) {
    this.#container = container;
    this.#document = pdfDocument;
    this.#onSelect = onSelect;
    this.#eventBus = eventBus;
  }

  mount(): void {
    this.#container.replaceChildren();
    const fragment = document.createDocumentFragment();
    const root = this.#container.parentElement;
    if ("IntersectionObserver" in window) {
      this.#observer = new IntersectionObserver(
        (entries) => {
          for (const entry of entries) {
            if (entry.isIntersecting) {
              const page = Number((entry.target as HTMLElement).dataset.pageNumber);
              if (Number.isInteger(page)) {
                this.#visiblePages.add(page);
                void this.#render(page);
              }
            } else {
              const page = Number((entry.target as HTMLElement).dataset.pageNumber);
              if (Number.isInteger(page)) this.#visiblePages.delete(page);
            }
          }
        },
        { root, rootMargin: "320px 0px" },
      );
    }

    for (let page = 1; page <= this.#document.numPages; page += 1) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "thumbnail-button";
      button.dataset.pageNumber = String(page);
      button.setAttribute("aria-label", `Ir a PDF page ${page}`);
      const canvas = document.createElement("canvas");
      canvas.setAttribute("aria-hidden", "true");
      const label = document.createElement("span");
      label.textContent = `p. ${page}`;
      button.append(canvas, label);
      button.addEventListener(
        "click",
        () => {
          if (button.dataset.renderError === "true") {
            this.#clearError(button);
            void this.#render(page);
          }
          this.#onSelect(page);
        },
        { signal: this.#abortController.signal },
      );
      this.#buttons.set(page, button);
      fragment.append(button);
      this.#observer?.observe(button);
    }
    this.#container.append(fragment);
    if (this.#observer === null && this.#document.numPages > 0) {
      this.#visiblePages.add(1);
      void this.#render(1);
    }
  }

  setCurrent(page: number): void {
    for (const [number, button] of this.#buttons) {
      const current = number === page;
      button.classList.toggle("is-current", current);
      if (current) {
        button.setAttribute("aria-current", "page");
        button.scrollIntoView({ block: "nearest" });
        void this.#render(number);
      } else {
        button.removeAttribute("aria-current");
      }
    }
  }

  setRotation(rotation: number): void {
    this.#rotation = rotation;
    this.#generation += 1;
    for (const { task } of this.#renderTasks.values()) {
      task.cancel();
    }
    this.#renderTasks.clear();
    this.#renderingGenerations.clear();
    for (const button of this.#buttons.values()) {
      delete button.dataset.rendered;
      delete button.dataset.rendering;
      this.#clearError(button);
    }
    const current = [...this.#buttons.entries()].find(([, button]) =>
      button.classList.contains("is-current"),
    );
    const pagesToRender = new Set(this.#visiblePages);
    if (current !== undefined) pagesToRender.add(current[0]);
    for (const page of pagesToRender) {
      void this.#render(page);
    }
  }

  destroy(): void {
    this.#destroyed = true;
    this.#generation += 1;
    this.#abortController.abort();
    this.#observer?.disconnect();
    for (const { task } of this.#renderTasks.values()) {
      task.cancel();
    }
    this.#renderTasks.clear();
    this.#renderingGenerations.clear();
    this.#visiblePages.clear();
    this.#buttons.clear();
    this.#container.replaceChildren();
  }

  async #render(pageNumber: number): Promise<void> {
    const button = this.#buttons.get(pageNumber);
    const generation = this.#generation;
    if (
      this.#destroyed ||
      button === undefined ||
      button.dataset.rendered === "true" ||
      this.#renderingGenerations.has(pageNumber)
    ) {
      return;
    }
    this.#renderingGenerations.set(pageNumber, generation);
    button.dataset.rendering = "true";
    try {
      const page = await this.#document.getPage(pageNumber);
      if (this.#destroyed || generation !== this.#generation) {
        return;
      }
      const baseViewport = page.getViewport({ scale: 1, rotation: this.#rotation });
      const viewport = page.getViewport({
        scale: THUMBNAIL_WIDTH / baseViewport.width,
        rotation: this.#rotation,
      });
      const canvas = button.querySelector("canvas");
      if (!(canvas instanceof HTMLCanvasElement)) {
        throw new Error("thumbnail_canvas_unavailable");
      }
      const context = canvas.getContext("2d", { alpha: false });
      if (context === null) {
        throw new Error("thumbnail_context_unavailable");
      }
      const outputScale = Math.min(window.devicePixelRatio || 1, MAX_OUTPUT_SCALE);
      canvas.width = Math.max(1, Math.floor(viewport.width * outputScale));
      canvas.height = Math.max(1, Math.floor(viewport.height * outputScale));
      canvas.style.width = `${Math.floor(viewport.width)}px`;
      canvas.style.height = `${Math.floor(viewport.height)}px`;
      const task = page.render({
        canvas,
        canvasContext: context,
        viewport,
        annotationMode: AnnotationMode.DISABLE,
        transform: outputScale === 1 ? undefined : [outputScale, 0, 0, outputScale, 0, 0],
      });
      this.#renderTasks.set(pageNumber, { generation, task });
      await task.promise;
      if (this.#destroyed || generation !== this.#generation) return;
      const paint = inspectCanvasPaint(canvas);
      if (!paint.painted) {
        throw new Error("blank_thumbnail_canvas");
      }
      if (!this.#destroyed) {
        button.dataset.rendered = "true";
        this.#clearError(button);
        this.#eventBus.dispatch("thumbnailrendered", {
          source: this,
          pageNumber,
          pdfPage: page,
          error: null,
        });
      }
    } catch (reason) {
      if (
        !this.#destroyed &&
        generation === this.#generation &&
        !(reason instanceof Error && reason.name === "RenderingCancelledException")
      ) {
        this.#showError(button);
        this.#eventBus.dispatch("thumbnailrendered", {
          source: this,
          pageNumber,
          error: "page_render_failed",
        });
      }
    } finally {
      if (this.#renderTasks.get(pageNumber)?.generation === generation) {
        this.#renderTasks.delete(pageNumber);
      }
      if (this.#renderingGenerations.get(pageNumber) === generation) {
        this.#renderingGenerations.delete(pageNumber);
        delete button.dataset.rendering;
      }
    }
  }

  #clearError(button: HTMLButtonElement): void {
    delete button.dataset.renderError;
    button.querySelector(":scope > .thumbnail-render-error")?.remove();
  }

  #showError(button: HTMLButtonElement): void {
    button.dataset.renderError = "true";
    if (button.querySelector(":scope > .thumbnail-render-error") !== null) return;
    const error = document.createElement("span");
    error.className = "thumbnail-render-error";
    error.textContent = "No renderizada · reintentar";
    button.append(error);
  }
}
