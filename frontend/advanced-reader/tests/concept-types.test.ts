import { describe, expect, it, vi } from "vitest";
import {
  DocumentEditor,
  renderDocument,
} from "../src/knowledge-map/document-editor";
import {
  conceptKind,
  conceptTypes,
  resultNames,
} from "../src/knowledge-map/concept-types";
import {
  applyStudyTheme,
  contrast,
  studyTheme,
} from "../src/knowledge-map/theme";
import { parseDocument, serialize } from "../src/knowledge-map/document";
import { conceptSample } from "../src/study/concept-sample";

vi.mock("../src/knowledge-map/keyboard", () => ({
  mountMathKeyboard: () => () => {},
}));
vi.mock("../src/knowledge-map/math", () => ({
  makeMath: (value: string) =>
    Object.assign(document.createElement("math-field"), {
      value,
      selection: { ranges: [[0, 0]], direction: "forward" },
    }),
  mathErrors: () => [],
}));

describe("MathMongo mathematical identity", () => {
  it("retains the real xcolor purple and the original remark alias", () => {
    expect(conceptTypes.lema.original).toBe("#BF0040");
    expect(conceptTypes.observacion.original).toBe("#008080");
    expect(resultNames.remark).toBe("Nota");
    expect(conceptKind("Proposición")).toBe("proposicion");
    for (const [kind, type] of Object.entries(conceptTypes))
      for (const alias of type.aliases) expect(conceptKind(alias)).toBe(kind);
    expect(conceptTypes.proposicion.shape).not.toBe(conceptTypes.ejemplo.shape);
    expect(conceptKind("error")).toBeUndefined();
    expect(conceptKind("Cornell")).toBeUndefined();
  });
  it("keeps every screen accent and body readable on their actual dark surfaces", () => {
    for (const type of Object.values(conceptTypes)) {
      expect(contrast(type.accent, type.background)).toBeGreaterThanOrEqual(
        4.5,
      );
      expect(contrast(type.accent, studyTheme.panel)).toBeGreaterThanOrEqual(
        4.5,
      );
      expect(contrast(studyTheme.text, type.background)).toBeGreaterThanOrEqual(
        4.5,
      );
    }
    const root = document.createElement("div");
    applyStudyTheme(root);
    expect(root.style.getPropertyValue("--concept-lema-accent")).toBe(
      conceptTypes.lema.accent,
    );
    expect(root.style.getPropertyValue("--mm-error")).toBe(studyTheme.error);
  });
  it("renders all eight mathematical families without rewriting original LaTeX", () => {
    const root = document.createElement("div");
    document.body.append(root);
    const dispose = renderDocument(root, conceptSample);
    expect(root.querySelectorAll("section[data-result]")).toHaveLength(8);
    for (const [kind, type] of Object.entries(conceptTypes)) {
      const block = root.querySelector(`[data-concept-type="${kind}"]`)!;
      expect(block.getAttribute("aria-label")).toBe(type.label);
      expect(
        block.querySelector("header")?.getAttribute("data-type-symbol"),
      ).toBe(type.symbol);
      expect(block.querySelectorAll("math-field")).toHaveLength(2);
    }
    dispose();
    root.remove();
    expect(serialize(parseDocument(conceptSample))).toBe(conceptSample);
  });
  it("preserves explicit document customizations while editing neighboring prose", () => {
    const original = String.raw`\definecolor{miAzul}{HTML}{224488}
\begin{cthteorema}[colback=miAzul!8,colframe=miAzul]{Título propio}
Texto con $\frac{a}{b}$.
\end{cthteorema}`;
    const root = document.createElement("div");
    document.body.append(root);
    const editor = new DocumentEditor(
      root,
      original + "\n\nPárrafo.",
      () => {},
    );
    editor.editor.commands.insertContentAt(
      editor.editor.state.doc.content.size - 1,
      " Más prosa.",
    );
    expect(editor.value()).toContain(original);
    expect(editor.value()).toContain("Más prosa.");
    expect(root.querySelector('[data-concept-type="teorema"]')).toBeNull();
    expect(root.textContent).toContain("Estilo personalizado conservado");
    const groups = root.querySelectorAll('[role="group"]');
    expect(groups).toHaveLength(5);
    expect(
      root.querySelector("select")?.querySelectorAll("option"),
    ).toHaveLength(10);
    editor.destroy();
    root.remove();
  });
  it("keeps source line wrapping as LaTeX whitespace instead of introducing hard breaks", () => {
    const source =
      String.raw`\begin{cthdefinicion}{Una idea}` +
      "\nTexto con $x$.\n" +
      String.raw`\end{cthdefinicion}`;
    const parsed = parseDocument(source);
    const paragraph = parsed.content![0].content![0];
    expect(
      paragraph
        .content!.filter((node) => node.type === "text")
        .every((node) => !node.text!.includes("\n")),
    ).toBe(true);
    expect(serialize(parsed)).toBe(source);
  });
});
