import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(cleanup);

// jsdom has no layout engine. Source-state tests use empty geometry; keyboard,
// scrolling and resized editors are exercised in the real browser suites.
if (!Range.prototype.getClientRects) {
  Range.prototype.getClientRects = () => [] as unknown as DOMRectList;
  Range.prototype.getBoundingClientRect = () => new DOMRect();
}
if (!document.execCommand) {
  // CodeMirror's shadow-selection fallback calls this browser API. jsdom has
  // neither native editing commands nor layout; real selection stays in E2E.
  document.execCommand = () => false;
}

// jsdom lacks native dialog methods; real focus/inert behavior is checked in
// Chrome and Firefox, while unit tests exercise the source-editing contract.
if (!HTMLDialogElement.prototype.showModal) {
  Object.defineProperties(HTMLDialogElement.prototype, {
    showModal: {
      configurable: true,
      writable: true,
      value(this: HTMLDialogElement) {
        this.setAttribute("open", "");
      },
    },
    close: {
      configurable: true,
      writable: true,
      value(this: HTMLDialogElement) {
        this.removeAttribute("open");
      },
    },
  });
}

Object.defineProperty(Element.prototype, "scrollIntoView", {
  configurable: true,
  value: () => undefined,
});

if (!("requestAnimationFrame" in window)) {
  Object.defineProperty(window, "requestAnimationFrame", {
    configurable: true,
    value: (callback: FrameRequestCallback) =>
      window.setTimeout(() => callback(Date.now()), 0),
  });
  Object.defineProperty(window, "cancelAnimationFrame", {
    configurable: true,
    value: (handle: number) => window.clearTimeout(handle),
  });
}

// Unit suites mount the actual CodeMirror synchronously. The loader boundary and
// delayed import teardown have their own tests; browsers exercise real chunks.
vi.mock("../src/latex/source-loader", async () => {
  const { LatexSourceEditor } = await import("../src/latex/source-editor");
  return { LatexSourceLoader: LatexSourceEditor };
});

// jsdom does not render constructable stylesheets. State tests model the platform
// shape only; Chrome/Firefox validate actual adopted CSS under the unchanged CSP.
if (!CSSStyleSheet.prototype.replaceSync) {
  CSSStyleSheet.prototype.replaceSync = function (_text: string) { /* No layout engine. */ };
}
if (!("adoptedStyleSheets" in ShadowRoot.prototype)) {
  const sheets = new WeakMap<ShadowRoot, CSSStyleSheet[]>();
  Object.defineProperty(ShadowRoot.prototype, "adoptedStyleSheets", {
    configurable: true,
    get(this: ShadowRoot) { return sheets.get(this) ?? []; },
    set(this: ShadowRoot, value: CSSStyleSheet[]) { sheets.set(this, value); },
  });
}
