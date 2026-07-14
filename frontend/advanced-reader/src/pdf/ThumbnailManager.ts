import { AnnotationMode } from "pdfjs-dist";
import type { PDFDocumentProxy, RenderTask } from "pdfjs-dist";

const THUMBNAIL_WIDTH = 132;
const MAX_OUTPUT_SCALE = 2;

export class ThumbnailManager {
  readonly #container: HTMLDivElement;
  readonly #document: PDFDocumentProxy;
  readonly #onSelect: (page: number) => void;
  readonly #buttons = new Map<number, HTMLButtonElement>();
  readonly #renderTasks = new Map<number, RenderTask>();
  readonly #abortController = new AbortController();
  #observer: IntersectionObserver | null = null;
  #rotation = 0;
  #destroyed = false;

  constructor(
    container: HTMLDivElement,
    pdfDocument: PDFDocumentProxy,
    onSelect: (page: number) => void,
  ) {
    this.#container = container;
    this.#document = pdfDocument;
    this.#onSelect = onSelect;
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
                void this.#render(page);
              }
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
      button.addEventListener("click", () => this.#onSelect(page), {
        signal: this.#abortController.signal,
      });
      this.#buttons.set(page, button);
      fragment.append(button);
      this.#observer?.observe(button);
    }
    this.#container.append(fragment);
    if (this.#observer === null && this.#document.numPages > 0) {
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
    for (const [page, task] of this.#renderTasks) {
      task.cancel();
      this.#renderTasks.delete(page);
    }
    for (const button of this.#buttons.values()) {
      delete button.dataset.rendered;
      delete button.dataset.rendering;
      this.#observer?.observe(button);
    }
    const current = [...this.#buttons.entries()].find(([, button]) =>
      button.classList.contains("is-current"),
    );
    if (current) {
      void this.#render(current[0]);
    }
  }

  destroy(): void {
    this.#destroyed = true;
    this.#abortController.abort();
    this.#observer?.disconnect();
    for (const task of this.#renderTasks.values()) {
      task.cancel();
    }
    this.#renderTasks.clear();
    this.#buttons.clear();
    this.#container.replaceChildren();
  }

  async #render(pageNumber: number): Promise<void> {
    const button = this.#buttons.get(pageNumber);
    if (
      this.#destroyed ||
      button === undefined ||
      button.dataset.rendered === "true" ||
      button.dataset.rendering === "true"
    ) {
      return;
    }
    button.dataset.rendering = "true";
    try {
      const page = await this.#document.getPage(pageNumber);
      if (this.#destroyed) {
        return;
      }
      const baseViewport = page.getViewport({ scale: 1, rotation: this.#rotation });
      const viewport = page.getViewport({
        scale: THUMBNAIL_WIDTH / baseViewport.width,
        rotation: this.#rotation,
      });
      const canvas = button.querySelector("canvas");
      if (!(canvas instanceof HTMLCanvasElement)) {
        return;
      }
      const context = canvas.getContext("2d", { alpha: false });
      if (context === null) {
        return;
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
      this.#renderTasks.set(pageNumber, task);
      await task.promise;
      if (!this.#destroyed) {
        button.dataset.rendered = "true";
        this.#observer?.unobserve(button);
      }
    } catch {
      // A cancelled or malformed thumbnail must not block the main viewer.
    } finally {
      this.#renderTasks.delete(pageNumber);
      delete button.dataset.rendering;
    }
  }
}
