import { afterEach, expect, it } from "vitest";
import { codeViewport } from "../src/latex/source-styles";
import { readFileSync } from "node:fs";
afterEach(() => document.body.replaceChildren());
it("shares one trusted stylesheet across source roots without inserting an inline style tag", () => {
  const first = document.createElement("div"),
    second = document.createElement("div");
  document.body.append(first, second);
  const a = codeViewport(first),
    b = codeViewport(second);
  expect(a.root.adoptedStyleSheets[0]).toBe(b.root.adoptedStyleSheets[0]);
  expect(a.root.querySelector("style")).toBeNull();
  expect(a.parent.classList.contains("code-root")).toBe(true);
});
it("declines unsupported stylesheet capabilities before mounting an unusable code root", () => {
  const descriptor = Object.getOwnPropertyDescriptor(
    CSSStyleSheet.prototype,
    "replaceSync",
  )!;
  Object.defineProperty(CSSStyleSheet.prototype, "replaceSync", {
    configurable: true,
    value: undefined,
  });
  try {
    const host = document.createElement("div");
    expect(() => codeViewport(host)).toThrow(
      "Constructable stylesheets unavailable",
    );
    expect(host.shadowRoot).toBeNull();
  } finally {
    Object.defineProperty(CSSStyleSheet.prototype, "replaceSync", descriptor);
  }
});
it("keeps the locally served Tiptap baseline equal to the installed pinned dependency", () => {
  const upstream = readFileSync(
    "node_modules/@tiptap/core/dist/index.js",
    "utf8",
  );
  const canonical = /const style = `([\s\S]+?)`;/u.exec(upstream)![1];
  const local = readFileSync("src/knowledge-map/document-base.css", "utf8");
  expect(local.slice(local.indexOf(".ProseMirror"))).toBe(canonical + "\n");
});
