import { describe, expect, it, vi } from "vitest";
import { MathfieldElement } from "mathlive";
import { makeMath, mathErrors } from "../src/knowledge-map/math";

vi.mock("mathlive", async (importOriginal) => {
  const actual = await importOriginal<typeof import("mathlive")>();
  class TestMathfield extends HTMLElement {
    value = "";
    readOnly = false;
    mathVirtualKeyboardPolicy = "";
  }
  customElements.define("adapter-test-mathfield", TestMathfield);
  return { ...actual, MathfieldElement: TestMathfield };
});

describe("MathLive adapter security and canonical content", () => {
  it("keeps the generated keyboard editable while removing active HTML", () => {
    const safe = String(
      MathfieldElement.createHTML!(
        "<span contenteditable=true>input</span><script>bad()</script><img src=x onerror=bad()>",
      ),
    );
    const container = document.createElement("div");
    container.innerHTML = safe;
    expect(
      container.querySelector("span")?.getAttribute("contenteditable"),
    ).toBe("true");
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")?.hasAttribute("onerror")).toBe(false);
  });
  it("configures local resources, no algebra engine, and explicit editability", () => {
    const latex = String.raw`\frac{b+a}{1}`;
    const editable = makeMath(latex, true),
      reader = makeMath(latex, false);
    expect(editable.value).toBe(latex);
    expect(reader.value).toBe(latex);
    expect(editable.readOnly).toBe(false);
    expect(reader.readOnly).toBe(true);
    expect(editable.mathVirtualKeyboardPolicy).toBe("manual");
    expect(MathfieldElement.fontsDirectory).toBeNull();
    expect(MathfieldElement.soundsDirectory).toBeNull();
    expect(MathfieldElement.computeEngine).toBeNull();
    const open = vi.spyOn(window, "open");
    MathfieldElement.openUrl?.("https://example.invalid");
    expect(open).not.toHaveBeenCalled();
  });
  it("uses the real LaTeX validator and distinguishes drafts from complete expressions", () => {
    expect(mathErrors(String.raw`\frac{1}{2}`)).toEqual([]);
    for (const input of [
      "",
      String.raw`\frac{1`,
      String.raw`x^`,
      String.raw`\frac{\placeholder{}}{2}`,
    ])
      expect(mathErrors(input).length).toBeGreaterThan(0);
  });
});
