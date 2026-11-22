import { describe, it, expect } from "vitest";
import { configureReaderTheme } from "../src/study-reader-theme";
describe("reader study presentation", () => {
  it("leaves ordinary reader preferences and PDF children untouched", () => {
    const root = document.createElement("div");
    root.innerHTML = '<canvas style="background: white"></canvas>';
    const before = root.outerHTML;
    configureReaderTheme(root, "?document_id=doc_test");
    expect(root.outerHTML).toBe(before);
    configureReaderTheme(root, "?theme=study&document_id=doc_test");
    expect(root.dataset.studyTheme).toBe("true");
    expect(root.style.getPropertyValue("--mm-bg")).toBe("#091A27");
    expect(root.querySelector("canvas")!.style.background).toBe("white");
    expect(localStorage.getItem("theme")).toBeNull();
  });
});
