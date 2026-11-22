import { afterEach, expect, it, vi } from "vitest";
import { mountMathKeyboard } from "../src/knowledge-map/keyboard";
afterEach(() => {
  vi.restoreAllMocks();
  document.body.replaceChildren();
});
it("adopts vendor sheets after a detached dialog is mounted, and restores its container", () => {
  const keyboard = Object.assign(new EventTarget(), {
    container: document.body as HTMLElement,
    hide: vi.fn(),
  });
  Object.defineProperty(window, "mathVirtualKeyboard", {
    configurable: true,
    value: keyboard,
  });
  const before = new CSSStyleSheet(),
    vendor = new CSSStyleSheet();
  Object.defineProperty(document, "adoptedStyleSheets", {
    configurable: true,
    writable: true,
    value: [before],
  });
  const host = document.createElement("div");
  document.body.append(host);
  const shadow = host.attachShadow({ mode: "open" });
  Object.defineProperty(shadow, "adoptedStyleSheets", {
    configurable: true,
    writable: true,
    value: [],
  });
  const dialog = document.createElement("dialog"),
    dispose = mountMathKeyboard(dialog);
  shadow.append(dialog);
  keyboard.dispatchEvent(new Event("before-virtual-keyboard-toggle"));
  document.adoptedStyleSheets = [before, vendor];
  keyboard.dispatchEvent(new Event("virtual-keyboard-toggle"));
  expect(shadow.adoptedStyleSheets).toContain(vendor);
  expect(shadow.adoptedStyleSheets).not.toContain(before);
  dispose();
  expect(keyboard.hide).toHaveBeenCalledTimes(1);
  expect(keyboard.container).toBe(document.body);
  const later = new CSSStyleSheet();
  document.adoptedStyleSheets = [later];
  keyboard.dispatchEvent(new Event("virtual-keyboard-toggle"));
  expect(shadow.adoptedStyleSheets).not.toContain(later);
});
it("keeps physical editing available when the optional virtual keyboard is unavailable", () => {
  Object.defineProperty(window, "mathVirtualKeyboard", {
    configurable: true,
    value: null,
  });
  expect(() =>
    mountMathKeyboard(document.createElement("div"))(),
  ).not.toThrow();
});
